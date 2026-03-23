import cv2
cap = cv2.VideoCapture(0)
ret, frame = cap.read()
if ret:
    cv2.imwrite("test_image.jpg", frame)
    print("照片已保存，摄像头工作正常！")
else:
    print("无法抓取图像")
cap.release()