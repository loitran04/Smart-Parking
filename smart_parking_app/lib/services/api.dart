import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../models/login_response.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'dart:io' show Platform;
import '../models/user_model.dart';

String get baseUrl {
  // if (kIsWeb) return 'http://localhost:8000';
  if (Platform.isAndroid) return 'http://10.0.2.2:8000'; // Android emulator
  return 'http://127.0.0.1:8000'; // iOS Simulator / desktop
}
  

class ApiService {
  //login
  static Future<LoginResponse?> login(String username, String password) async {
    final url = Uri.parse("${baseUrl}/auth/login/");
    final response = await http.post(
      url,
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({"username": username, "password": password}),
    );

    if (response.statusCode == 200) {
      final data = json.decode(response.body) as Map<String, dynamic>;
      final loginRes = LoginResponse.fromJson(data);

      // lưu token để dùng về sau
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('auth_token', loginRes.token);
      await prefs.setString('user_id', loginRes.userId);

      return loginRes;
    } else {
      return null;
    }
  }
  //register
  static Future<bool> registerUser({
    required String username,
    required String email,
    required String fullName,
    required String password,
    String? phone,
  }) async {
    final url = Uri.parse("${baseUrl}/auth/register/");

    final response = await http.post(
      url,
      headers: {'Content-Type': 'application/x-www-form-urlencoded'},
      body: {
        'username': username,
        'email': email,
        'full_name': fullName,
        'password': password,
        if (phone != null) 'phone': phone,
      },
    );

    // Backend của bạn có thể trả 200 hoặc 201 khi tạo thành công
    return response.statusCode == 200 || response.statusCode == 201;
  }



  static Future<Map<String, dynamic>?> getQr() async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString("auth_token"); // <-- sửa key

    if (token == null) return null;

    final url = Uri.parse("$baseUrl/parking/register/");
    final res = await http.post(url, headers: {"Authorization": "Token $token"});

    // API trả 201 theo BE; chấp nhận mọi 2xx
    if (res.statusCode >= 200 && res.statusCode < 300) {
      return jsonDecode(res.body) as Map<String, dynamic>;
    }
    if (kIsWeb) {
      // tiện debug khi chạy web
      // ignore: avoid_print
      print('getQr ERROR ${res.statusCode} - ${res.body}');
    }
    return null;
  }
  

  static Future<UserModel?> me() async {
  final prefs = await SharedPreferences.getInstance();
  final token = prefs.getString('auth_token');
  if (token == null) return null;

  final url = Uri.parse("${baseUrl}/auth/me/");
  final response = await http.get(
    url,
    headers: {
      'Authorization': 'Token $token',
      'Accept': 'application/json',
    },
  );

  if (response.statusCode == 200) {
    final data = json.decode(response.body) as Map<String, dynamic>;
    final user = UserModel.fromJson(data);
    await prefs.setString('user_json', jsonEncode(user.toJson()));
    return user;
  }

  // Token hết hạn → dọn cache (tùy chọn)
  if (response.statusCode == 401) {
    await prefs.remove('auth_token');
    await prefs.remove('user_json');
  }
  return null;
}
/// Lấy user từ cache (nếu có)
  static Future<UserModel?> getCachedUser() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString('user_json');
    if (raw == null) return null;
    return UserModel.fromJson(jsonDecode(raw) as Map<String, dynamic>);
  }

/// Cập nhật thông tin hồ sơ (PATCH /auth/changeInfo/)
  static Future<UserModel?> changeInfo({
    String? fullName,
    String? email,
    String? phone,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString('auth_token');
    if (token == null) return null;

    final url = Uri.parse("${baseUrl}/auth/changeInfo/");
    final body = <String, dynamic>{};
    if (fullName != null) body['full_name'] = fullName;
    if (email != null) body['email'] = email;
    if (phone != null) body['phone'] = phone;

    final res = await http.patch(
      url,
      headers: {
        'Authorization': 'Token $token',
        'Content-Type': 'application/json',
      },
      body: jsonEncode(body),
    );

    if (res.statusCode == 200) {
      final user = UserModel.fromJson(jsonDecode(res.body));
      await prefs.setString('user_json', jsonEncode(user.toJson()));
      return user;
    }
    return null;
  }

  /// Đổi mật khẩu (POST /auth/changePassword/)
  static Future<bool> changePassword(String oldPwd, String newPwd) async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString('auth_token');
    if (token == null) return false;

    final url = Uri.parse("${baseUrl}/auth/changePassword/");
    final res = await http.post(
      url,
      headers: {
        'Authorization': 'Token $token',
        'Content-Type': 'application/json',
      },
      body: jsonEncode({'old_password': oldPwd, 'new_password': newPwd}),
    );
    return res.statusCode == 200;
  }

  /// Đăng xuất (gọi API + xoá cache)
  static Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString('auth_token');

    if (token != null) {
      final url = Uri.parse("${baseUrl}/auth/logout/");
      try {
        await http.post(url, headers: {'Authorization': 'Token $token'});
      } catch (_) {}
    }
    await prefs.remove('auth_token');
    await prefs.remove('user_json');
  }

}
