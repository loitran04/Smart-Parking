import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../models/login_response.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'dart:io' show Platform;
import '../models/user_model.dart';
import '../models/reservation_model.dart';
import '../models/payment_model.dart';

String getBaseUrl() {
  if (kIsWeb) return 'http://localhost:8000';
  if (Platform.isAndroid) return 'http://10.0.2.2:8000';
  return 'http://localhost:8000'; 
}

final String baseUrl = getBaseUrl();

class ApiService {
  ApiService({String? baseUrl, this.authScheme = 'Token'})
    : _baseOverride = baseUrl;
  final String? _baseOverride;
  final String authScheme;
  String _base() => _baseOverride ?? baseUrl;

  Future<Map<String, String>> _headers() async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString('auth_token');
    return {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
      if (token != null && token.isNotEmpty)
        'Authorization': '$authScheme $token',
    };
  }

  Future<List<Map<String, dynamic>>> listTariffs() async {
    final r = await http.get(
      Uri.parse('${_base()}/tariffs/'),
      headers: await _headers(),
    );
    if (r.statusCode != 200)
      throw Exception('Tariffs GET ${r.statusCode}: ${r.body}');
    return List<Map<String, dynamic>>.from(json.decode(r.body));
  }

  Future<Map<String, dynamic>> createTariff(Map<String, dynamic> body) async {
    final r = await http.post(
      Uri.parse('${_base()}/tariffs/'),
      headers: await _headers(),
      body: json.encode(body),
    );
    if (r.statusCode != 201)
      throw Exception('Tariff POST ${r.statusCode}: ${r.body}');
    return json.decode(r.body);
  }

  Future<Map<String, dynamic>> updateTariff(
    String id,
    Map<String, dynamic> body,
  ) async {
    final r = await http.put(
      Uri.parse('${_base()}/tariffs/$id/'),
      headers: await _headers(),
      body: json.encode(body),
    );
    if (r.statusCode != 200)
      throw Exception('Tariff PUT ${r.statusCode}: ${r.body}');
    return json.decode(r.body);
  }

  Future<void> deleteTariff(String id) async {
    final r = await http.delete(
      Uri.parse('${_base()}/tariffs/$id/'),
      headers: await _headers(),
    );
    if (r.statusCode != 204)
      throw Exception('Tariff DELETE ${r.statusCode}: ${r.body}');
  }

  Future<List<Map<String, dynamic>>> listGates() async {
    final r = await http.get(
      Uri.parse('${_base()}/gates/'),
      headers: await _headers(),
    );
    if (r.statusCode != 200)
      throw Exception('Gates GET ${r.statusCode}: ${r.body}');
    return List<Map<String, dynamic>>.from(json.decode(r.body));
  }

  Future<Map<String, dynamic>> createGate(Map<String, dynamic> body) async {
    final r = await http.post(
      Uri.parse('${_base()}/gates/'),
      headers: await _headers(),
      body: json.encode(body),
    );
    if (r.statusCode != 201)
      throw Exception('Gate POST ${r.statusCode}: ${r.body}');
    return json.decode(r.body);
  }

  Future<Map<String, dynamic>> updateGate(
    String id,
    Map<String, dynamic> body,
  ) async {
    final r = await http.put(
      Uri.parse('${_base()}/gates/$id/'),
      headers: await _headers(),
      body: json.encode(body),
    );
    if (r.statusCode != 200)
      throw Exception('Gate PUT ${r.statusCode}: ${r.body}');
    return json.decode(r.body);
  }

  Future<void> deleteGate(String id) async {
    final r = await http.delete(
      Uri.parse('${_base()}/gates/$id/'),
      headers: await _headers(),
    );
    if (r.statusCode != 204)
      throw Exception('Gate DELETE ${r.statusCode}: ${r.body}');
  }

  static Future<LoginResponse?> login(String username, String password) async {
    final url = Uri.parse("${baseUrl}/auth/login/");
    final response = await http.post(
      url,
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({"username": username, "password": password}),
    );

    print('Response status: ${response.statusCode}');
    print('Response body: ${response.body}'); 
    if (response.statusCode == 200) {
      final data = json.decode(response.body) as Map<String, dynamic>;
      final loginRes = LoginResponse.fromJson(data);

      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('auth_token', loginRes.token);
      await prefs.setString('user_id', loginRes.userId);

      if (data['user'] != null) {
        await prefs.setString('user_json', jsonEncode(data['user']));
      } else {
        await me();
      }

      return loginRes;
    } else {
      return null;
    }
  }

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

    return response.statusCode == 200 || response.statusCode == 201;
  }

  static Future<Map<String, dynamic>?> getQr() async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString("auth_token"); 

    if (token == null) return null;

    final url = Uri.parse("$baseUrl/parking/register/");
    final res = await http.post(
      url,
      headers: {"Authorization": "Token $token"},
    );

    if (res.statusCode >= 200 && res.statusCode < 300) {
      return jsonDecode(res.body) as Map<String, dynamic>;
    }
    if (kIsWeb) {
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
      headers: {'Authorization': 'Token $token', 'Accept': 'application/json'},
    );

    if (response.statusCode == 200) {
      final data = json.decode(response.body) as Map<String, dynamic>;
      final user = UserModel.fromJson(data);
      await prefs.setString('user_json', jsonEncode(user.toJson()));
      return user;
    }

    if (response.statusCode == 401) {
      await prefs.remove('auth_token');
      await prefs.remove('user_json');
    }
    return null;
  }

  static Future<UserModel?> getCachedUser() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString('user_json');
    if (raw == null) return null;
    return UserModel.fromJson(jsonDecode(raw) as Map<String, dynamic>);
  }

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

  static Future<ReservationModel?> createReservation({
    required String vehicleType, 
    required DateTime startTime,
    required int durationMinutes, 
  }) async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString('auth_token');
    if (token == null) return null;

    final url = Uri.parse("$baseUrl/parking/register/");
    final res = await http.post(
      url,
      headers: {
        'Authorization': 'Token $token',
        'Content-Type': 'application/json',
      },
      body: jsonEncode({
        'vehicle_type': vehicleType,
        'start_time': startTime.toUtc().toIso8601String(),
        'duration_minutes': durationMinutes,
      }),
    );

    if (res.statusCode >= 200 && res.statusCode < 300) {
      return ReservationModel.fromJson(jsonDecode(res.body));
    }
    return null;
  }

  static Future<List<ReservationModel>> myReservations() async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString('auth_token');
    if (token == null) return [];
    final url = Uri.parse("$baseUrl/parking/reservations/");
    final res = await http.get(url, headers: {'Authorization': 'Token $token'});
    if (res.statusCode == 200) {
      final List list = jsonDecode(res.body) as List;
      return list
          .map((e) => ReservationModel.fromJson(e as Map<String, dynamic>))
          .toList();
    }
    return [];
  }

  static Future<ReservationModel?> reservationDetail(String id) async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString('auth_token');
    if (token == null) return null;
    final url = Uri.parse("$baseUrl/parking/reservations/$id/");
    final res = await http.get(url, headers: {'Authorization': 'Token $token'});
    if (res.statusCode == 200) {
      return ReservationModel.fromJson(
        jsonDecode(res.body) as Map<String, dynamic>,
      );
    }
    return null;
  }

  static Future<List<PaymentModel>> myPayments({String? status}) async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString('auth_token');
    if (token == null) throw Exception('Chưa đăng nhập');

    final uri = Uri.parse(
      '$baseUrl/parking/payments/${status != null ? '?status=$status' : ''}',
    );

    final res = await http.get(
      uri,
      headers: {
        'Authorization': 'Token $token',
        'Content-Type': 'application/json',
      },
    );

    if (res.statusCode != 200) {
      throw Exception(
        'Tải lịch sử thanh toán thất bại: ${res.statusCode} - ${res.body}',
      );
    }

    final data = jsonDecode(res.body) as List;
    return data
        .map((e) => PaymentModel.fromJson(e as Map<String, dynamic>))
        .toList();
  }
}
