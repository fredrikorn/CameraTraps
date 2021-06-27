echo. && echo SETTING PYTHON PATH:
set PYTHONPATH=c:\git\CameraTraps\CameraTraps;c:\git\ai4eutils

if not exist "output" mkdir output

python CameraTraps/detection/run_tf_detector_batch.py ./md_v4.1.0.pb images ./output/output.json
python output_record.py