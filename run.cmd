echo. && echo SETTING PYTHON PATH:
set PYTHONPATH=c:\git\cameratraps;c:\git\ai4eutils

python cameratraps/detection/run_tf_detector_batch.py ./md_v4.1.0.pb test_images ./some_output_file.json