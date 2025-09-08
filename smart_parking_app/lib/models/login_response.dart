class LoginResponse {
  final String token;
  final String userId;
  final bool is_staff;

  LoginResponse({
    required this.token,
    required this.userId,
    required this.is_staff,
  });

  factory LoginResponse.fromJson(Map<String, dynamic> json) {
    
    return LoginResponse(
      token: json['token'],
      userId: json['user_id'],
      is_staff: json['is_admin'] ?? false,
    );
  }
}
