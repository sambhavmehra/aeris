#!/usr/bin/env python3
"""
AERIS Advanced Features Verification Script
Performs unit-like integration testing on NLP, ML, Analytics, Cloud, Vision, and Assistant services.
"""
import os
import sys
import json
import shutil
from pathlib import Path

# Add backend directory to path so we can import services correctly
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Import services
try:
    from services.nlp_service import nlp_service
    from services.ml_service import ml_service
    from services.analytics_service import analytics_service
    from services.cloud_service import cloud_service
    from services.vision_engine import VisionEngine
    from services.virtual_assistant_service import assistant_service
    print("[SUCCESS] Imported all advanced feature services successfully.")
except Exception as e:
    print(f"[ERROR] Failed to import services: {e}")
    sys.exit(1)


def run_nlp_tests():
    print("\n--- Running NLP Service Tests ---")
    text = "Google DeepMind has a wonderful office in California. The engineers are building intelligent agents today."
    print(f"Input text: '{text}'")
    
    results = nlp_service.analyze_text(text)
    print("NLP Analysis Results:")
    print(json.dumps(results, indent=2))
    
    # Assertions / Validations
    sentiment = results.get("sentiment", {})
    assert sentiment.get("label") in ["positive", "neutral", "negative"], "Invalid sentiment label"
    assert len(results.get("tokens", [])) > 0, "No tokens extracted"
    assert any(ent["text"] == "California" for ent in results.get("entities", [])), "California entity missing"
    print("[PASS] NLP Service tests passed.")


def run_ml_tests():
    print("\n--- Running ML Service Tests ---")
    
    # 1. Linear Regression
    print("1. Testing Linear Regression...")
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [2.0, 4.0, 5.8, 8.2, 10.0]  # roughly y = 2x
    target_x = 6.0
    reg_res = ml_service.predict_linear_regression(x, y, target_x)
    print("Regression Results:", json.dumps(reg_res, indent=2))
    assert reg_res.get("success"), "Linear regression failed"
    assert abs(reg_res["prediction"] - 12.0) < 0.5, f"Regression prediction out of bounds: {reg_res['prediction']}"
    
    # 2. K-Means Clustering
    print("\n2. Testing K-Means Clustering...")
    coords = [[1.0, 1.0], [1.2, 0.9], [1.1, 1.1], [10.0, 10.0], [10.5, 9.8], [9.8, 10.2]]
    cluster_res = ml_service.cluster_kmeans(coords, n_clusters=2)
    print("Clustering Results:", json.dumps(cluster_res, indent=2))
    assert cluster_res.get("success"), "K-Means clustering failed"
    labels = cluster_res["labels"]
    assert labels[0] == labels[1] == labels[2], "First three points should be in the same cluster"
    assert labels[3] == labels[4] == labels[5], "Last three points should be in the same cluster"
    assert labels[0] != labels[3], "The two groups of points should belong to different clusters"
    
    # 3. Random Forest Classification
    print("\n3. Testing Classification...")
    train_features = [[1.0, 1.0], [1.1, 1.2], [5.0, 5.0], [5.2, 4.8]]
    train_labels = ["TypeA", "TypeA", "TypeB", "TypeB"]
    test_features = [[1.05, 1.15], [5.1, 4.9]]
    clf_res = ml_service.classify_data(train_features, train_labels, test_features)
    print("Classification Results:", json.dumps(clf_res, indent=2))
    assert clf_res.get("success"), "Classification failed"
    assert clf_res["predictions"][0] == "TypeA", "First test sample prediction incorrect"
    assert clf_res["predictions"][1] == "TypeB", "Second test sample prediction incorrect"
    
    print("[PASS] ML Service tests passed.")


def run_analytics_tests():
    print("\n--- Running Data Analytics Tests ---")
    # Setup temporary CSV file
    temp_csv = BACKEND_DIR / "scratch" / "temp_test_data.csv"
    temp_csv.parent.mkdir(parents=True, exist_ok=True)
    
    csv_content = (
        "id,name,val1,val2\n"
        "1,alpha,10.0,100.0\n"
        "2,beta,15.5,120.0\n"
        "3,gamma,20.0,150.0\n"
        "4,delta,25.0,180.0\n"
        "5,epsilon,30.0,200.0\n"
    )
    
    with open(temp_csv, "w") as f:
        f.write(csv_content)
        
    try:
        # 1. Summarize CSV
        print("1. Testing CSV Summarization...")
        summary = analytics_service.summarize_csv(str(temp_csv))
        print("Summary Results:", json.dumps(summary, indent=2))
        assert summary.get("success"), "CSV summary failed"
        assert summary["shape"]["rows"] == 5, "Row count mismatch"
        assert "val1" in summary["numeric_statistics"], "Numeric summary missing columns"
        
        # 2. Correlation CSV
        print("\n2. Testing Correlation Calculation...")
        corr = analytics_service.calculate_correlation(str(temp_csv))
        print("Correlation Results:", json.dumps(corr, indent=2))
        assert corr.get("success"), "Correlation failed"
        assert "val1" in corr["correlation_matrix"], "Correlation matrix missing columns"
        
        print("[PASS] Analytics Service tests passed.")
    finally:
        if temp_csv.exists():
            temp_csv.unlink()


def run_cloud_tests():
    print("\n--- Running Cloud Service Tests ---")
    
    # Setup a temporary file to upload
    temp_upload = BACKEND_DIR / "scratch" / "temp_cloud_upload.txt"
    with open(temp_upload, "w") as f:
        f.write("Hello cloud simulation from AERIS!")
        
    try:
        bucket = "aeris-verification-bucket"
        obj_name = "test_upload.txt"
        
        # 1. Create Bucket
        print("1. Creating cloud bucket...")
        res = cloud_service.storage_operation("create_bucket", bucket_name=bucket)
        print(res)
        assert res.get("success"), "Bucket creation failed"
        
        # 2. Upload File
        print("\n2. Uploading file...")
        res = cloud_service.storage_operation("upload_file", file_path=str(temp_upload), bucket_name=bucket, object_name=obj_name)
        print(res)
        assert res.get("success"), "Upload failed"
        
        # 3. List Bucket
        print("\n3. Listing bucket...")
        res = cloud_service.storage_operation("list_bucket", bucket_name=bucket)
        print(res)
        assert res.get("success"), "List failed"
        assert any(obj["object_name"] == obj_name for obj in res["objects"]), "Uploaded object not listed"
        
        # 4. Download File
        temp_download = BACKEND_DIR / "scratch" / "temp_cloud_download.txt"
        print("\n4. Downloading file...")
        res = cloud_service.storage_operation("download_file", file_path=str(temp_download), bucket_name=bucket, object_name=obj_name)
        print(res)
        assert res.get("success"), "Download failed"
        assert temp_download.exists(), "Downloaded file does not exist"
        with open(temp_download, "r") as f:
            content = f.read()
        assert content == "Hello cloud simulation from AERIS!", f"Downloaded content mismatch: {content}"
        
        # 5. Delete File
        print("\n5. Deleting file...")
        res = cloud_service.storage_operation("delete_file", bucket_name=bucket, object_name=obj_name)
        print(res)
        assert res.get("success"), "Deletion failed"
        
        # 6. VM Provisioning Simulation
        print("\n6. Testing VM Provisioning...")
        res = cloud_service.provision_instance(instance_type="m5.large", region="eu-west-1")
        print("VM Provisioning Results:", json.dumps(res, indent=2))
        assert res.get("success"), "Instance provisioning failed"
        assert res["instance_type"] == "m5.large", "Instance type mismatch"
        assert res["status"] == "running", "Instance status incorrect"
        
        print("[PASS] Cloud Service tests passed.")
        
    finally:
        if temp_upload.exists():
            temp_upload.unlink()
        if (BACKEND_DIR / "scratch" / "temp_cloud_download.txt").exists():
            (BACKEND_DIR / "scratch" / "temp_cloud_download.txt").unlink()
        # Clean up cloud bucket simulator dir if needed
        bucket_dir = cloud_service.cloud_root / bucket
        if bucket_dir.exists():
            shutil.rmtree(bucket_dir)


def run_vision_tests():
    print("\n--- Running Computer Vision Tests ---")
    
    # Create a simple dummy image using numpy/opencv
    import numpy as np
    import cv2
    
    temp_img = BACKEND_DIR / "scratch" / "temp_cv_test.png"
    temp_img.parent.mkdir(parents=True, exist_ok=True)
    
    # Create a 200x200 image with a white square on a grey background
    img = np.zeros((200, 200, 3), dtype=np.uint8) + 100
    cv2.rectangle(img, (50, 50), (150, 150), (255, 255, 255), -1)
    cv2.imwrite(str(temp_img), img)
    
    engine = VisionEngine()
    
    filters_to_test = ["grayscale", "blur", "edge", "threshold"]
    output_files = []
    
    try:
        for ftype in filters_to_test:
            print(f"Applying filter: {ftype}...")
            res = engine.apply_cv_filter(str(temp_img), ftype)
            print("CV Filter Results:", json.dumps(res, indent=2))
            assert res.get("success"), f"Failed to apply {ftype} filter"
            out_path = res["path"]
            assert os.path.exists(out_path), f"Processed image file not found: {out_path}"
            output_files.append(out_path)
            
        print("[PASS] Computer Vision (OpenCV) filter tests passed.")
    finally:
        # Clean up input image
        if temp_img.exists():
            temp_img.unlink()
        # Clean up processed output images
        for fpath in output_files:
            if os.path.exists(fpath):
                os.unlink(fpath)


def run_assistant_tests():
    print("\n--- Running Virtual Assistant Service Tests ---")
    
    # Backup existing log if any
    backup_exists = assistant_service.log_file.exists()
    backup_logs = []
    if backup_exists:
        backup_logs = assistant_service._load_logs()
        
    try:
        # Write clean state
        assistant_service._save_logs([])
        
        # Test personalization recommendation fallback
        print("1. Testing empty logs recommendation...")
        res = assistant_service.get_personalized_recommendations()
        print(res)
        assert res.get("success"), "Personalized recommendations failed on empty logs"
        assert "Welcome to AERIS" in res["recommendation"], "Fallback recommendation mismatch"
        
        # Test logging turns and system recommendation triggers
        print("\n2. Logging interaction turns for system preference...")
        assistant_service.log_interaction("check the CPU load", "CPU usage is 10%.")
        assistant_service.log_interaction("battery and system diagnostics status", "Battery is at 98%.")
        assistant_service.log_interaction("how much free RAM is left?", "Free memory is 12GB.")
        
        res = assistant_service.get_personalized_recommendations()
        print("System Recommendation:", json.dumps(res, indent=2))
        assert res.get("success")
        assert "schedule_execution" in res["recommendation"], "Personalized suggestion should recommend scheduling system monitors"
        assert res["total_turns_analyzed"] == 3
        
        # Test developer preference
        print("\n3. Logging interaction turns for developer preference...")
        assistant_service._save_logs([])
        assistant_service.log_interaction("write a python script for regression", "I have generated code.py.")
        assistant_service.log_interaction("build this project codebase", "Starting the build compilation.")
        
        res = assistant_service.get_personalized_recommendations()
        print("Developer Recommendation:", json.dumps(res, indent=2))
        assert res.get("success")
        assert "Antigravity IDE" in res["recommendation"], "Personalized suggestion should recommend IDE developer tools"
        
        print("[PASS] Virtual Assistant Service tests passed.")
        
    finally:
        # Restore backup logs
        if backup_exists:
            assistant_service._save_logs(backup_logs)
        else:
            if assistant_service.log_file.exists():
                assistant_service.log_file.unlink()


def main():
    print("====================================================")
    print("AERIS ADVANCED CAPABILITIES INTEGRATION VERIFICATION")
    print("====================================================")
    
    try:
        run_nlp_tests()
        run_ml_tests()
        run_analytics_tests()
        run_cloud_tests()
        run_vision_tests()
        run_assistant_tests()
        
        print("\n====================================================")
        print("ALL VERIFICATION TESTS PASSED SUCCESSFULLY!")
        print("====================================================")
        sys.exit(0)
    except AssertionError as ae:
        print(f"\n[FAIL] Assertion failed during validation: {ae}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[FAIL] Unexpected error occurred during validation: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
