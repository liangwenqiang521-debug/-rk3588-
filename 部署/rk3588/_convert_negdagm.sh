cd /root/rknn_convert
PYTHONPATH=/root/rknn_convert/libs python3 export_rknn.py --src best_negdagm.onnx --dst best_negdagm.rknn --imgsz 640 --names crazing inclusion patches pitted_surface rolled-in_scale scratches --dtype fp16
