class UserModel {
  final String id;
  final String username;
  final String? fullName;
  final String? phone;
  final String? email;

  UserModel({
    required this.id,
    required this.username,
    this.fullName,
    this.phone,
    this.email,
  });

  factory UserModel.fromJson(Map<String, dynamic> j) => UserModel(
        id: j['id'] as String,
        username: j['username'] as String,
        fullName: j['full_name'] as String?,
        phone: j['phone'] as String?,
        email: j['email'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'username': username,
        'full_name': fullName,
        'phone': phone,
        'email': email,
      };
}
