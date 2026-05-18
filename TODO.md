# TODO — Chat Display Upgrade + PDF Report Generation

## Frontend
- [ ] Install/confirm dependencies: react-markdown, remark-gfm, react-syntax-highlighter (+ a theme)
- [ ] Refactor `FRONTEND/src/components/ChatMessage.tsx` to use `react-markdown`
- [ ] Add premium styling via `ReactMarkdown` component overrides (tables, blockquotes, lists, headings)
- [ ] Keep `[IMAGE:url]` parsing by splitting content into segments (images + markdown text)
- [ ] Wire code blocks to `react-syntax-highlighter` for fenced code blocks

## Backend
- [ ] Add new tool `generate_pdf_report` to `BACKEND/tools/tool_registry.py`
- [ ] Implement tool using `BACKEND/services/file_converter.py`:
  - markdown_content -> temp .md -> md->html
  - html -> pdf
- [ ] Save output in `backend/data/reports` and return the exact pdf path
- [ ] Validate tool registration so it’s only used when explicitly requested

## Validation
- [ ] Frontend: run build/typecheck to ensure TS/React compilation passes
- [ ] Backend: run a minimal tool execution path to confirm PDF is produced and path is returned
