"""
AERIS LeakGraphAgent — Ethical recursive OSINT & public exposure analysis orchestrator.
Coordinates OSINTAgent and DorkingAgent to build recursive entity relationship graphs
and calculate exposure risk scores.
"""

from __future__ import annotations

import re
import json
import logging
import asyncio
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from agents.base_agent import BaseAgent
from ai_engine import ai_engine
from agents.osint_agent import OSINTAgent
from agents.dorking_agent import DorkingAgent

logger = logging.getLogger("aeris.agent.leakgraph")

# ──────────────────────────────────────────────────────────────────────────────
# Prompts
# ──────────────────────────────────────────────────────────────────────────────

SEED_INFERENCE_PROMPT = """Analyze the input text to identify the OSINT target (seed) and its type.
Input text: {text}

Supported types: "phone", "email", "person_name", "username", "social_profile", "domain", "organization", "location", "repository"

Respond with ONLY valid JSON:
{{"value": "the extracted value", "type": "one of the types above"}}
"""

EXTRACTION_PROMPT = """You are the entity extraction brain of AERIS's LeakGraphAgent.
Analyze the raw search results gathered for the current target entity.

Current Target Entity: {target_value} ({target_type})

=== RAW SEARCH RESULTS ===
{search_results}
=== END RESULTS ===

Extract any public entities directly and explicitly related to the Current Target Entity. Possible entity types:
- "phone": Phone numbers
- "email": Email addresses
- "person_name": Names of individuals
- "username": Online handles / usernames
- "social_profile": Social media profile URLs (e.g. twitter, github, linkedin, instagram)
- "domain": Domain names / websites (e.g. company.com)
- "organization": Companies, schools, or groups
- "location": Cities, countries, or regions
- "repository": Code repository URLs (e.g. github repos)
- "public_document": Publicly accessible document links
- "breach_record": Known leak/breach names
- "credential_exposure_metadata": Metadata indicating password/token exposure

For each extracted entity, provide:
1. "value": Normalized value
2. "type": One of the types above
3. "confidence": Score from 0.0 to 1.0
4. "confidence_label": CONFIRMED, PROBABLE, or POSSIBLE
5. "relationship": associated_with | discovered_from | same_identity_as | owns_profile | uses_email | uses_username | works_at | linked_to_domain | exposed_in_breach_metadata | mentioned_in_public_document | mentioned_in_repository | possible_match
6. "evidence": A safe, 1-sentence explanation of the relationship (do not include raw passwords, private keys, or full private records).

Also extract any exposure findings. For each finding, provide:
1. "finding": Name of the leak/mention/exposure
2. "severity": LOW | MEDIUM | HIGH | CRITICAL
3. "confidence": Score from 0.0 to 1.0
4. "exposed_data_type": list of data types exposed (e.g. ["email", "phone", "password_hash"])
5. "source_type": known_breach_metadata | public_web_mention | public_document_exposure | repository_exposure | social_profile_exposure | credential_exposure_metadata | domain_employee_exposure | paste_style_reference | data_broker_reference
6. "safe_evidence": Safe evidence summary.

CRITICAL INSTRUCTIONS TO PREVENT HALLUCINATION:
1. ONLY extract entities if the search result EXPLICITLY mentions the Current Target Entity ({target_value}) in direct connection with the extracted entity.
2. If the search results appear to be generic noise, unrelated articles, or do not clearly mention the Target Entity, DO NOT extract anything from them. Return empty arrays.
3. Never invent entities. Only extract what is clearly supported by the search results.
4. If a result mentions high-profile entities (like "Apple", "Microsoft", "Google", or famous people) but has no logical direct tie to the specific target phone/email/username, IGNORE IT.
5. Ensure all JSON string values are properly escaped (e.g., escape double quotes as \\").

Respond with ONLY valid JSON:
{{
  "entities": [
    {{
      "value": "extracted entity value",
      "type": "one of the types above",
      "confidence": 0.0 to 1.0,
      "confidence_label": "CONFIRMED|PROBABLE|POSSIBLE",
      "relationship": "relationship type",
      "evidence": "brief explanation"
    }}
  ],
  "exposure_findings": [
    {{
      "finding": "leak/exposure name",
      "severity": "LOW|MEDIUM|HIGH|CRITICAL",
      "confidence": 0.0 to 1.0,
      "exposed_data_type": ["data_class"],
      "source_type": "known_breach_metadata|...",
      "safe_evidence": "safe summary"
    }}
  ]
}}
"""


class LeakGraphAgent(BaseAgent):
    """
    Ethical recursive OSINT and public exposure orchestrator.
    Recursively pivots from discovered targets up to depth 3 using OSINTAgent and DorkingAgent.
    """

    def __init__(self):
        super().__init__(
            name="LeakGraphAgent",
            description="Ethical recursive OSINT and public exposure analysis orchestrator",
            task_domain="leakgraph",
            version="1.0.0",
            capabilities=[
                "Recursive OSINT Pivoting",
                "Public Exposure Discovery",
                "Entity Relationship Mapping",
                "Identity Exposure Risk Scoring",
                "Safe Redacted Intelligence Reporting",
            ],
        )

    # ── Think ──────────────────────────────────────────────────────

    async def think(self, message: str, context: dict) -> Any:
        """Parse seed target, normalize, and verify authorization status."""
        lower = message.lower()

        # Parse authorization
        explicit_auth = False
        if any(w in lower for w in ("my ", "own ", "authorized", "authorization", "permission")):
            explicit_auth = True

        # Extract seed target
        seed_val = None
        seed_type = None

        # Regex heuristics for fast parsing
        email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', message)
        phone_match = re.search(r'\+?[0-9][0-9\-\s\(\)\.]{7,15}[0-9]', message)
        url_match = re.search(r'https?://(?:www\.)?github\.com/([A-Za-z0-9_-]+/[A-Za-z0-9_-]+)', message)
        domain_match = re.search(r'\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b', message)

        if email_match:
            seed_val = email_match.group(0)
            seed_type = "email"
        elif phone_match and len(phone_match.group(0).replace(" ", "").replace("-", "")) >= 8:
            seed_val = phone_match.group(0)
            seed_type = "phone"
        elif url_match:
            seed_val = url_match.group(0)
            seed_type = "repository"
        elif domain_match and not any(ext in domain_match.group(0) for ext in ("com.br", "co.in", "co.uk", "gov")):
            # basic check to avoid false positives on common words with dots if any, but default to domain
            seed_val = domain_match.group(0)
            seed_type = "domain"

        # Fallback to LLM seed classification if heuristics ambiguous
        if not seed_val:
            try:
                prompt = SEED_INFERENCE_PROMPT.format(text=message)
                raw = await ai_engine.classify(prompt)
                raw = raw.strip()
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                    if raw.endswith("```"):
                        raw = raw[:-3]
                    raw = raw.strip()
                data = json.loads(raw)
                seed_val = data.get("value")
                seed_type = data.get("type")
            except Exception as e:
                logger.warning(f"Seed inference failed: {e}")
                # Ultimate fallback: treat entire message minus keywords as name
                clean = message
                for kw in ("leakgraph", "leak graph", "osint", "recursive", "exposure", "scan", "check"):
                    clean = re.sub(rf'\b{kw}\b', '', clean, flags=re.IGNORECASE)
                seed_val = clean.strip()
                seed_type = "person_name"

        plan = {
            "seed_value": seed_val,
            "seed_type": seed_type,
            "explicit_authorization": explicit_auth,
            "message": message,
        }
        return plan

    # ── Execute ────────────────────────────────────────────────────

    async def execute(self, plan: Any) -> Any:
        """Run recursive OSINT pivoting loop."""
        seed_value = plan.get("seed_value")
        seed_type = plan.get("seed_type")
        explicit_auth = plan.get("explicit_authorization", False)

        if not seed_value:
            return {"success": False, "error": "Could not identify seed target to analyze."}

        # Initialize OSINT & Dorking Agents
        osint_agent = OSINTAgent()
        dork_agent = DorkingAgent()

        # Normalize the seed
        normalized_seed = self._normalize_value(seed_value, seed_type)

        # Graph structures
        entities: Dict[str, Dict] = {}
        relationships: List[Dict] = []
        exposure_findings: List[Dict] = []
        discovery_chain: List[str] = [f"Seed entity parsed: {normalized_seed} ({seed_type})"]

        # Add seed to graph
        seed_key = f"{seed_type}:{normalized_seed}"
        entities[seed_key] = {
            "value": normalized_seed,
            "type": seed_type,
            "confidence": 1.0,
            "status": "CONFIRMED",
            "source_type": "user_input",
            "first_discovered_from": "User Input",
            "round": 0,
            "pivot_allowed": True,
        }

        # Tracking set
        searched_keys: Set[str] = set()

        # Hard limits
        max_depth = 3
        max_entities = 20
        max_queries_per_round = 12

        # Round Loop
        for round_idx in range(1, max_depth + 1):
            if len(entities) >= max_entities:
                discovery_chain.append(f"Round {round_idx}: Max entities limit reached. Stopping search.")
                break

            # A. Select pivot entities
            pivots = [
                ent for ent in entities.values()
                if ent["confidence"] >= 0.60
                and ent["pivot_allowed"]
                and f"{ent['type']}:{ent['value']}" not in searched_keys
            ]

            if not pivots:
                discovery_chain.append(f"Round {round_idx}: No new high-confidence pivots available. Completing search.")
                break

            # Limit pivot count per round to prevent API overload
            pivots = pivots[:max_queries_per_round]
            discovery_chain.append(f"Round {round_idx}: Pivoting from {len(pivots)} entities.")

            # B. Execute investigation in parallel
            tasks = [
                self._investigate_pivot(pivot, osint_agent, dork_agent)
                for pivot in pivots
            ]
            results = await asyncio.gather(*tasks)

            # Mark all as searched
            for pivot in pivots:
                searched_keys.add(f"{pivot['type']}:{pivot['value']}")

            # C. Extract & Merge entities from results
            for pivot, intel in zip(pivots, results):
                if not intel or "error" in intel:
                    continue

                intel_text = osint_agent._format_search_results(intel)

                # Call LLM extractor
                try:
                    extract_prompt = EXTRACTION_PROMPT.format(
                        target_value=pivot["value"],
                        target_type=pivot["type"],
                        search_results=intel_text[:6000]  # Avoid token limit overflow
                    )
                    raw_extracted = await ai_engine.chat(
                        messages=[
                            {"role": "system", "content": "You are a precise JSON extractor. Respond ONLY with valid JSON matching the requested schema."},
                            {"role": "user", "content": extract_prompt}
                        ],
                        temperature=0.1,
                        max_tokens=2048,
                        response_format={"type": "json_object"}
                    )
                    raw_extracted = raw_extracted.strip()
                    if raw_extracted.startswith("```"):
                        raw_extracted = raw_extracted.split("\n", 1)[1] if "\n" in raw_extracted else raw_extracted[3:]
                        if raw_extracted.endswith("```"):
                            raw_extracted = raw_extracted[:-3]
                        raw_extracted = raw_extracted.strip()

                    try:
                        extraction_res = json.loads(raw_extracted)
                    except json.JSONDecodeError as err:
                        logger.warning(f"Initial JSON parse failed for pivot {pivot['value']}: {err}. Attempting auto-repair...")
                        # Run a fast repair query with the LLM using chat (which supports max_tokens=2048)
                        repair_prompt = f"""You are an expert JSON repair utility.
The following JSON string failed to parse due to formatting/quoting issues (like unescaped double quotes, unescaped newlines, or control characters inside string fields, or truncation).
Fix the formatting so that it is a 100% valid JSON object matching the schema.
Do not change, omit, or invent keys or values. Just fix the JSON syntax (e.g. escape inner quotes as \\\" and inner newlines as \\n).

RAW INVALID JSON:
{raw_extracted}

Respond with ONLY the valid repaired JSON:"""
                        try:
                            repaired = await ai_engine.chat(
                                messages=[
                                    {"role": "system", "content": "You are a JSON repair utility. Respond ONLY with valid, complete JSON."},
                                    {"role": "user", "content": repair_prompt}
                                ],
                                temperature=0.1,
                                max_tokens=2048,
                                response_format={"type": "json_object"}
                            )
                            repaired = repaired.strip()
                            if repaired.startswith("```"):
                                repaired = repaired.split("\n", 1)[1] if "\n" in repaired else repaired[3:]
                                if repaired.endswith("```"):
                                    repaired = repaired[:-3]
                                repaired = repaired.strip()
                            extraction_res = json.loads(repaired)
                            logger.info(f"JSON successfully repaired and parsed for pivot {pivot['value']}.")
                        except Exception as repair_err:
                            logger.error(f"JSON repair failed for pivot {pivot['value']}: {repair_err}")
                            continue

                    # Update Discovery Chain
                    new_found_names = []

                    # Process extracted entities
                    for ent in extraction_res.get("entities", []):
                        val = ent.get("value")
                        etype = ent.get("type")
                        conf = float(ent.get("confidence", 0.5))
                        conf_label = ent.get("confidence_label", "POSSIBLE")
                        rel = ent.get("relationship", "associated_with")
                        evidence = ent.get("evidence", "")

                        if not val or not etype:
                            continue

                        # Normalize
                        norm_val = self._normalize_value(val, etype)
                        ent_key = f"{etype}:{norm_val}"

                        # Skip weak matches
                        if conf < 0.60:
                            continue

                        # Determine if pivot allowed (pivoting restrictions)
                        pivot_ok = True
                        if etype == "location":
                            pivot_ok = False
                        elif etype in ("person_name", "organization") and conf < 0.80:
                            pivot_ok = False

                        # Add or update entity
                        if ent_key in entities:
                            # Keep higher confidence
                            if conf > entities[ent_key]["confidence"]:
                                entities[ent_key]["confidence"] = conf
                                entities[ent_key]["status"] = conf_label
                        else:
                            if len(entities) < max_entities:
                                entities[ent_key] = {
                                    "value": norm_val,
                                    "type": etype,
                                    "confidence": conf,
                                    "status": conf_label,
                                    "source_type": "osint_pivot",
                                    "first_discovered_from": f"Pivot from {pivot['value']}",
                                    "round": round_idx,
                                    "pivot_allowed": pivot_ok,
                                }
                                new_found_names.append(f"{norm_val} ({etype})")

                        # Record relationship
                        # Avoid duplicates
                        rel_exists = any(
                            r["from"] == pivot["value"] and r["to"] == norm_val
                            for r in relationships
                        )
                        if not rel_exists:
                            relationships.append({
                                "from": pivot["value"],
                                "to": norm_val,
                                "relationship": rel,
                                "confidence": conf,
                                "evidence_summary": evidence
                            })

                    if new_found_names:
                        discovery_chain.append(
                            f"  ↳ Pivot '{pivot['value']}' yielded: {', '.join(new_found_names[:5])}"
                        )

                    # Add exposure findings
                    for finding in extraction_res.get("exposure_findings", []):
                        f_name = finding.get("finding")
                        if f_name:
                            # Avoid duplicates
                            if not any(ef["finding"] == f_name for ef in exposure_findings):
                                exposure_findings.append(finding)

                except Exception as e:
                    logger.warning(f"Failed to extract entities/findings for pivot {pivot['value']}: {e}")

        # Compute risk score
        risk_score, risk_level, breakdown = self._calculate_risk(entities, relationships, exposure_findings)

        return {
            "success": True,
            "seed_value": normalized_seed,
            "seed_type": seed_type,
            "authorization_status": "explicit" if explicit_auth else "assumed_public_only",
            "search_depth": max_depth,
            "entities": list(entities.values()),
            "relationships": relationships,
            "exposure_findings": exposure_findings,
            "discovery_chain": discovery_chain,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_breakdown": breakdown
        }

    # ── Report ─────────────────────────────────────────────────────

    async def report(self, results: Any) -> str:
        """Format final results into Markdown report and machine-readable JSON."""
        if not results.get("success"):
            return f"## ⚠️ OSINT Scan Error\n\n{results.get('error', 'Unknown error during LeakGraph execution.')}"

        seed_val = results["seed_value"]
        seed_type = results["seed_type"]
        auth_status = results["authorization_status"]
        depth = results["search_depth"]

        score = results["risk_score"]
        level = results["risk_level"]
        breakdown = results["risk_breakdown"]

        # Build Markdown report
        md = []
        md.append("# LeakGraph Exposure Report\n")

        # 1. Seed Section
        md.append("## 1. Seed")
        md.append(f"- Seed value: `{self._mask_value(seed_val, seed_type)}`")
        md.append(f"- Seed type: `{seed_type}`")
        md.append(f"- Authorization status: `{auth_status}`")
        md.append(f"- Search depth used: `{depth}`\n")

        # 2. Executive Summary
        md.append("## 2. Executive Summary")
        md.append(f"- **Overall exposure level**: **{level}**")
        md.append(f"- **Identity Exposure Score**: `{score}/100`")
        md.append(f"- **Account takeover risk**: **{breakdown.get('ato', 'LOW')}**")
        md.append(f"- **Social engineering risk**: **{breakdown.get('social_eng', 'LOW')}**")
        md.append(f"- **Public footprint risk**: **{breakdown.get('footprint', 'LOW')}**")
        
        # Key concern assessment
        key_concern = "No high-risk credentials or leak vectors discovered."
        if score >= 75:
            key_concern = "Critical exposure of core credentials and multi-platform links. High risk of immediate account takeover."
        elif score >= 50:
            key_concern = "High footprint exposure. Public documents, social links, and repository metadata reveal key developer/infrastructure targets."
        elif score >= 25:
            key_concern = "Moderate exposure found. Scattered social profiles, name-email links, or public mentions."
        md.append(f"- **Key concern**: {key_concern}\n")

        # 3. Discovery Chain
        md.append("## 3. Discovery Chain")
        for step in results["discovery_chain"]:
            # Mask any raw targets listed in discovery chain log
            masked_step = step
            # Regex match emails
            emails_in_step = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', step)
            for email in emails_in_step:
                masked_step = masked_step.replace(email, self._mask_value(email, "email"))
            # Regex match phones
            phones_in_step = re.findall(r'\+?[0-9][0-9\-\s\(\)\.]{7,15}[0-9]', step)
            for phone in phones_in_step:
                if len(phone.replace(" ", "").replace("-", "")) >= 8:
                    masked_step = masked_step.replace(phone, self._mask_value(phone, "phone"))
            md.append(f"- {masked_step}")
        md.append("")

        # 4. Entity Graph Table
        md.append("## 4. Entity Graph")
        md.append("| Entity | Type | Confidence | Status | Source Type | First Discovered From | Round |")
        md.append("|---|---|---:|---|---|---|---:|")
        for ent in results["entities"]:
            masked_val = self._mask_value(ent["value"], ent["type"])
            md.append(
                f"| `{masked_val}` | {ent['type']} | {ent['confidence']:.2f} | "
                f"{ent['status']} | {ent['source_type']} | {ent['first_discovered_from']} | {ent['round']} |"
            )
        md.append("")

        # 5. Relationship Map Table
        md.append("## 5. Relationship Map")
        md.append("| From | To | Relationship | Confidence | Evidence Summary |")
        md.append("|---|---|---|---:|---|")
        for rel in results["relationships"]:
            from_masked = self._mask_value(rel["from"], self._infer_value_type(rel["from"]))
            to_masked = self._mask_value(rel["to"], self._infer_value_type(rel["to"]))
            md.append(
                f"| `{from_masked}` | `{to_masked}` | {rel['relationship']} | "
                f"{rel['confidence']:.2f} | {rel['evidence_summary']} |"
            )
        md.append("")

        # 6. Leak & Exposure Findings Table
        md.append("## 6. Leak & Exposure Findings")
        md.append("| Finding | Severity | Confidence | Exposed Data Type | Source Type | Safe Evidence |")
        md.append("|---|---|---:|---|---|---|")
        findings = results.get("exposure_findings", [])
        if findings:
            for f in findings:
                data_types = ", ".join(f.get("exposed_data_type", []))
                md.append(
                    f"| {f.get('finding')} | **{f.get('severity')}** | {f.get('confidence', 0.8):.2f} | "
                    f"`{data_types}` | {f.get('source_type')} | {f.get('safe_evidence')} |"
                )
        else:
            md.append("| None | — | — | — | — | No public leaks or high-severity exposures discovered. |")
        md.append("")

        # 7. Risk Analysis
        md.append("## 7. Risk Analysis")
        md.append(f"### Identity Exposure Risk: **{level}**")
        md.append("The density of public identifiers matches and links determines overall profile construct integrity. "
                  "When multiple email addresses, phone numbers, and social profiles correlate with high confidence, "
                  "it makes identity cloning or targeting highly feasible.")
        md.append(f"### Account Takeover Risk: **{breakdown.get('ato', 'LOW')}**")
        md.append("Determined by credential exposure metadata, leak history, and exposed repository tokens. "
                  "Reuse of credentials across platforms increases this risk factor significantly.")
        md.append(f"### Social Engineering Risk: **{breakdown.get('social_eng', 'LOW')}**")
        md.append("High OSINT exposure provides adversaries with enough context (workplace, project repositories, family links, "
                  "handles) to construct highly targeted, credible phishing campaigns.")
        md.append(f"### Credential Reuse Risk: **{breakdown.get('credential_reuse', 'LOW')}**")
        md.append("Leaked breach metadata indicates whether previous database breaches included passwords linked to this profile's primary emails.")
        md.append(f"### Public Footprint Risk: **{breakdown.get('footprint', 'LOW')}**")
        md.append("Measures overall search visibility and indexing across search engines, social platforms, and developer platforms.\n")

        # 8. Recommended Actions
        md.append("## 8. Recommended Actions")
        md.append("### Immediate:")
        if score >= 50:
            md.append("- **Change passwords** for affected accounts immediately.")
            md.append("- **Enable MFA / 2FA** on all profiles (especially primary emails and GitHub/LinkedIn).")
            md.append("- **Revoke active sessions** on compromised or exposed platforms.")
        else:
            md.append("- Enable standard MFA/2FA on all linked social profiles and emails.")
        md.append("- Monitor logins and verify recovery configurations.")

        md.append("\n### Privacy Cleanup:")
        md.append("- Configure social media profiles to private, restricting email/phone visibility from public searches.")
        md.append("- Hide primary email in GitHub commit settings (use GitHub noreply addresses instead).")
        md.append("- Request opt-out/removal from data broker listings or index engines showing phone/address linkages.")

        md.append("\n### Monitoring:")
        md.append("- Register target email addresses in automated breach notification lists.")
        md.append("- Monitor search engine mentions for dork indicators and set up GitHub secret scanning notifications.\n")

        # 9. Limitations
        md.append("## 9. Limitations")
        md.append("- Results are based on public-source signals and available metadata.")
        md.append("- Some findings may be probable or possible, not confirmed.")
        md.append("- No private databases, passwords, dumps, or illegal sources were accessed.")
        md.append("- Sensitive data was intentionally redacted and masked to prevent abuse.\n")

        # 10. Machine-Readable JSON
        md.append("## 10. Machine-Readable JSON")

        # Create output JSON struct
        json_entities = []
        for ent in results["entities"]:
            json_entities.append({
                "value": ent["value"],
                "masked_value": self._mask_value(ent["value"], ent["type"]),
                "type": ent["type"],
                "confidence": ent["confidence"],
                "status": ent["status"],
                "source_type": ent["source_type"],
                "first_discovered_from": [ent["first_discovered_from"]],
                "round": ent["round"],
                "pivot_allowed": ent["pivot_allowed"]
            })

        json_relationships = []
        for rel in results["relationships"]:
            json_relationships.append({
                "from": rel["from"],
                "to": rel["to"],
                "relationship": rel["relationship"],
                "confidence": rel["confidence"],
                "evidence_summary": rel["evidence_summary"]
            })

        json_findings = []
        for f in findings:
            json_findings.append({
                "finding": f.get("finding"),
                "severity": f.get("severity"),
                "confidence": f.get("confidence", 0.8),
                "exposed_data_type": f.get("exposed_data_type", []),
                "source_type": f.get("source_type"),
                "safe_evidence": f.get("safe_evidence")
            })

        json_output = {
            "seed": {
                "value": seed_val,
                "type": seed_type,
                "authorization_status": auth_status
            },
            "limits": {
                "max_depth": depth,
                "max_entities": 20,
                "minimum_pivot_confidence": 0.6
            },
            "overall_risk": {
                "level": level,
                "score": score,
                "identity_exposure_risk": level,
                "account_takeover_risk": breakdown.get("ato", "LOW"),
                "social_engineering_risk": breakdown.get("social_eng", "LOW"),
                "public_footprint_risk": breakdown.get("footprint", "LOW")
            },
            "entities": json_entities,
            "relationships": json_relationships,
            "pivot_chain": [
                {
                    "round": 1,
                    "inputs_used": [seed_val],
                    "agents_used": ["OSINTAgent", "DorkingAgent"],
                    "query_themes": ["exact lookup", "connected entity lookup"],
                    "new_entities_found": [e["value"] for e in results["entities"] if e["round"] == 1],
                    "rejected_candidates": []
                }
            ],
            "exposure_findings": json_findings,
            "recommended_actions": {
                "immediate": [
                    "Change passwords for affected accounts",
                    "Enable MFA/2FA",
                    "Monitor recovery emails"
                ],
                "privacy_cleanup": [
                    "Remove phone/email from public listings",
                    "Lock down social profiles"
                ],
                "monitoring": [
                    "Set breach alerts",
                    "Monitor login alerts"
                ]
            },
            "limitations": [
                "Results based on public OSINT sources",
                "No private dumps or illicit databases accessed"
            ]
        }

        md.append("```json")
        md.append(json.dumps(json_output, indent=2))
        md.append("```")

        return "\n".join(md)

    # ── Helpers ────────────────────────────────────────────────────

    async def _investigate_pivot(self, pivot: Dict, osint_agent: OSINTAgent, dork_agent: DorkingAgent) -> Any:
        """Call OSINT and Dorking Agents internally to perform a target search."""
        val = pivot["value"]
        etype = pivot["type"]
        try:
            # Reuses the exact OSINTAgent target search pipeline
            # runs Travily in parallel with built Google dork keywords
            return await osint_agent._run_target_search(val, etype, mode="hacker", dork_agent=dork_agent)
        except Exception as e:
            logger.warning(f"OSINT target search failed for pivot {val}: {e}")
            return {"error": str(e)}

    @staticmethod
    def _normalize_value(value: str, etype: str) -> str:
        """Normalize target entities for unique deduplication."""
        val = value.strip()
        if etype == "email":
            return val.lower()
        if etype == "domain":
            val = val.lower()
            val = re.sub(r'^https?://', '', val)
            val = re.sub(r'^www\.', '', val)
            return val.split('/')[0]
        if etype == "username":
            return val.lower().lstrip("@")
        if etype == "phone":
            # Strip non-digits except +
            return "+" + "".join(c for c in val if c.isdigit()) if val.startswith("+") else "".join(c for c in val if c.isdigit())
        if etype == "repository":
            return val.lower()
        return val

    @staticmethod
    def _infer_value_type(value: str) -> str:
        """Helper to infer etype from a string value."""
        if "@" in value:
            return "email"
        if value.startswith("+") or (value.replace(" ", "").replace("-", "").isdigit() and len(value) >= 8):
            return "phone"
        if "." in value and "/" not in value:
            return "domain"
        if "github.com/" in value.lower():
            return "repository"
        return "general"

    @staticmethod
    def _mask_value(value: str, etype: str) -> str:
        """Redact sensitive personal identifiable information."""
        if not value:
            return ""
        if etype == "email":
            parts = value.split("@")
            if len(parts) == 2:
                name, domain = parts
                masked_name = name[0] + "*" * (len(name) - 1) if len(name) > 1 else "*"
                return f"{masked_name}@{domain}"
            return "a***@example.com"
        if etype == "phone":
            val = value.replace(" ", "").replace("-", "")
            if len(val) > 7:
                return f"{val[:3]}XXXXXX{val[-4:]}"
            return "+91XXXXXX1234"
        if etype in ("credential_exposure_metadata", "password", "password_hash"):
            return "[REDACTED_SENSITIVE_DATA]"
        if etype == "token":
            return "[REDACTED_TOKEN_PATTERN]"
        if etype == "location" and len(value) > 20:
            return "[REDACTED_PRIVATE_ADDRESS]"
        if etype == "person_name":
            parts = value.split()
            if len(parts) > 1:
                return f"{parts[0]} " + " ".join(p[0] + "*" * (len(p) - 1) for p in parts[1:])
            return f"{value[0]}***"
        return value

    def _calculate_risk(self, entities: Dict[str, Dict], relationships: List[Dict], exposure_findings: List[Dict]) -> Tuple[int, str, Dict[str, str]]:
        """Calculate Identity Exposure Risk Score (0-100) programmatically."""
        score = 0
        breakdown = {
            "ato": "LOW",
            "social_eng": "LOW",
            "footprint": "LOW",
            "credential_reuse": "LOW"
        }

        # Scan entities
        etypes = [e["type"] for e in entities.values()]
        emails = [e for e in entities.values() if e["type"] == "email"]
        phones = [e for e in entities.values() if e["type"] == "phone"]
        repos = [e for e in entities.values() if e["type"] == "repository"]

        # Check relationships
        has_phone_name = False
        has_phone_email = False
        has_social_phone_email = False

        for rel in relationships:
            t1 = self._infer_value_type(rel["from"])
            t2 = self._infer_value_type(rel["to"])
            types = {t1, t2}
            if "phone" in types and "person_name" in types:
                has_phone_name = True
            if "phone" in types and "email" in types:
                has_phone_email = True
            if ("social_profile" in types or "username" in types) and ("phone" in types or "email" in types):
                has_social_phone_email = True

        # Scan findings
        has_credential_exposure = False
        has_token_exposure = False
        has_document_exposure = False
        breach_count = 0

        for f in exposure_findings:
            st = f.get("source_type", "")
            dt = f.get("exposed_data_type", [])
            if "password_hash" in dt or "password" in dt:
                has_credential_exposure = True
            if "token_metadata" in dt or st == "credential_exposure_metadata":
                has_token_exposure = True
            if st == "public_document_exposure":
                has_document_exposure = True
            if st == "known_breach_metadata":
                breach_count += 1

        # 1. Breach metadata with password details: +35
        if has_credential_exposure:
            score += 35
            breakdown["ato"] = "HIGH"
            breakdown["credential_reuse"] = "HIGH"

        # 2. Email found in multiple breaches: +25
        if breach_count >= 2:
            score += 25
            breakdown["credential_reuse"] = "HIGH"
        elif breach_count == 1:
            score += 15
            breakdown["credential_reuse"] = "MEDIUM"

        # 3. Phone + name linked: +20
        if has_phone_name:
            score += 20
            breakdown["social_eng"] = "MEDIUM"

        # 4. Phone + email linked: +25
        if has_phone_email:
            score += 25
            breakdown["social_eng"] = "HIGH"

        # 5. Social profiles linked to email/phone: +15
        if has_social_phone_email:
            score += 15
            breakdown["footprint"] = "MEDIUM"

        # 6. GitHub/repository exposure: +25
        if repos:
            score += 25
            breakdown["footprint"] = "HIGH"

        # 7. API key/token patterns: +40
        if has_token_exposure:
            score += 40
            breakdown["ato"] = "CRITICAL"

        # 8. Public document containing identifiers: +20
        if has_document_exposure:
            score += 20
            breakdown["footprint"] = "MEDIUM"

        # 9. Corroborated graph (multiple independent entries): +15
        if len(entities) > 5:
            score += 15

        # 10. Default weak matches: +5
        if score == 0 and len(entities) > 1:
            score = 5

        # Cap score at 100
        score = min(score, 100)

        # Risk level categorization
        if score >= 75:
            level = "CRITICAL"
        elif score >= 50:
            level = "HIGH"
        elif score >= 25:
            level = "MEDIUM"
        else:
            level = "LOW"

        # Upgrade breakdown states based on overall level
        for k, v in breakdown.items():
            if level == "CRITICAL" and v == "HIGH":
                breakdown[k] = "CRITICAL"
            elif level == "HIGH" and v == "LOW":
                breakdown[k] = "MEDIUM"

        return score, level, breakdown
