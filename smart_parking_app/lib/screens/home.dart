import 'package:flutter/material.dart';
import 'package:smart_parking_app/services/api.dart';  // Để gọi API

class HomeScreen extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text("Smart Parking")),
      body: Center(
        child: ElevatedButton(
          onPressed: () async {
            // Gọi API lấy QR
            final qrData = await ApiService.getQr();
            if (qrData != null) {
              print("Mã QR: ${qrData['value']}");
              // Hiển thị QR hoặc dùng logic khác để gửi xe
            } else {
              print("Không có mã QR hoặc lỗi");
            }
          },
          child: Text("Lấy Mã QR Gửi Xe"),
        ),
      ),
    );
  }
}
