import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../services/api.dart';

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _formKey = GlobalKey<FormState>();
  final _fullNameCtrl = TextEditingController();
  final _usernameCtrl = TextEditingController();
  final _emailCtrl = TextEditingController();
  final _phoneCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  final _confirmCtrl = TextEditingController();

  bool _obscure1 = true;
  bool _obscure2 = true;
  bool _loading = false;

  @override
  void dispose() {
    _fullNameCtrl.dispose();
    _usernameCtrl.dispose();
    _emailCtrl.dispose();
    _phoneCtrl.dispose();
    _passCtrl.dispose();
    _confirmCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _loading = true);

    final ok = await ApiService.registerUser(
      username: _usernameCtrl.text.trim(),
      email: _emailCtrl.text.trim(),
      fullName: _fullNameCtrl.text.trim(),
      password: _passCtrl.text,
      phone: _phoneCtrl.text.trim().isEmpty ? null : _phoneCtrl.text.trim(),
    );

    setState(() => _loading = false);
    if (!mounted) return;

    if (ok) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Đăng ký thành công! Hãy đăng nhập.')),
      );
      context.goNamed('home');  // → vào Home
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Đăng ký thất bại, vui lòng thử lại.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final colorPrimary = const Color(0xFFF24E4E);
    final colorPrimaryDark = const Color(0xFFE03434);

    InputDecoration deco({
      required String label,
      IconData? icon,
      Widget? suffix,
    }) {
      return InputDecoration(
        labelText: label,
        prefixIcon: icon == null ? null : Icon(icon),
        suffixIcon: suffix,
        filled: true,
        fillColor: const Color(0xFFF9FAFB),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Color(0xFFE6E8EC)),
        ),
      );
    }

    return Scaffold(
      backgroundColor: const Color(0xFFF7F7FB),
      body: SafeArea(
        child: Stack(
          children: [
            Container(
              height: 260,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [colorPrimary, colorPrimaryDark],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: const BorderRadius.only(
                  bottomLeft: Radius.circular(36),
                  bottomRight: Radius.circular(36),
                ),
              ),
            ),
            SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(20, 28, 20, 20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SizedBox(height: 8),
                  Center(
                    child: Container(
                      width: 86,
                      height: 86,
                      decoration: BoxDecoration(
                        color: Colors.white,
                        shape: BoxShape.circle,
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withOpacity(.08),
                            blurRadius: 16,
                            offset: const Offset(0, 8),
                          )
                        ],
                      ),
                      child: const Icon(Icons.person_add_alt_1, size: 40, color: Colors.black54),
                    ),
                  ),
                  const SizedBox(height: 18),
                  const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 6),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Create Account',
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 28,
                              fontWeight: FontWeight.w700,
                            )),
                        SizedBox(height: 6),
                        Text('Join us to continue.',
                            style: TextStyle(color: Colors.white70, fontSize: 15)),
                      ],
                    ),
                  ),
                  const SizedBox(height: 22),

                  // Card form
                  Container(
                    margin: const EdgeInsets.symmetric(horizontal: 4),
                    padding: const EdgeInsets.fromLTRB(18, 18, 18, 24),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(18),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withOpacity(.06),
                          blurRadius: 18,
                          offset: const Offset(0, 8),
                        )
                      ],
                    ),
                    child: Form(
                      key: _formKey,
                      child: Column(
                        children: [
                          TextFormField(
                            controller: _fullNameCtrl,
                            textInputAction: TextInputAction.next,
                            decoration: deco(label: 'Họ và tên', icon: Icons.badge_outlined),
                            validator: (v) =>
                                (v == null || v.trim().isEmpty) ? 'Nhập họ và tên' : null,
                          ),
                          const SizedBox(height: 12),
                          TextFormField(
                            controller: _usernameCtrl,
                            textInputAction: TextInputAction.next,
                            decoration: deco(label: 'Tài khoản', icon: Icons.person_outline),
                            validator: (v) =>
                                (v == null || v.trim().isEmpty) ? 'Nhập tài khoản' : null,
                          ),
                          const SizedBox(height: 12),
                          TextFormField(
                            controller: _emailCtrl,
                            textInputAction: TextInputAction.next,
                            keyboardType: TextInputType.emailAddress,
                            decoration: deco(label: 'Email', icon: Icons.mail_outline),
                            validator: (v) {
                              if (v == null || v.trim().isEmpty) return 'Nhập email';
                              final ok = RegExp(r'^[^@]+@[^@]+\.[^@]+').hasMatch(v.trim());
                              return ok ? null : 'Email không hợp lệ';
                            },
                          ),
                          const SizedBox(height: 12),
                          TextFormField(
                            controller: _phoneCtrl,
                            textInputAction: TextInputAction.next,
                            keyboardType: TextInputType.phone,
                            decoration: deco(label: 'Số điện thoại (tuỳ chọn)', icon: Icons.phone_outlined),
                          ),
                          const SizedBox(height: 12),
                          TextFormField(
                            controller: _passCtrl,
                            obscureText: _obscure1,
                            textInputAction: TextInputAction.next,
                            decoration: deco(
                              label: 'Mật khẩu (≥ 6 ký tự)',
                              icon: Icons.lock_outline,
                              suffix: IconButton(
                                onPressed: () => setState(() => _obscure1 = !_obscure1),
                                icon: Icon(_obscure1 ? Icons.visibility_off : Icons.visibility),
                              ),
                            ),
                            validator: (v) =>
                                (v == null || v.length < 6) ? 'Mật khẩu tối thiểu 6 ký tự' : null,
                          ),
                          const SizedBox(height: 12),
                          TextFormField(
                            controller: _confirmCtrl,
                            obscureText: _obscure2,
                            textInputAction: TextInputAction.done,
                            onFieldSubmitted: (_) => _submit(),
                            decoration: deco(
                              label: 'Xác nhận mật khẩu',
                              icon: Icons.verified_user_outlined,
                              suffix: IconButton(
                                onPressed: () => setState(() => _obscure2 = !_obscure2),
                                icon: Icon(_obscure2 ? Icons.visibility_off : Icons.visibility),
                              ),
                            ),
                            validator: (v) =>
                                (v != _passCtrl.text) ? 'Mật khẩu không khớp' : null,
                          ),
                          const SizedBox(height: 18),
                          SizedBox(
                            width: double.infinity,
                            height: 52,
                            child: ElevatedButton(
                              onPressed: _loading ? null : _submit,
                              style: ElevatedButton.styleFrom(
                                backgroundColor: colorPrimary,
                                foregroundColor: Colors.white,
                                elevation: 0,
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(28),
                                ),
                              ),
                              child: _loading
                                  ? const SizedBox(
                                      width: 22,
                                      height: 22,
                                      child: CircularProgressIndicator(strokeWidth: 2),
                                    )
                                  : const Text(
                                      'Create Account',
                                      style: TextStyle(
                                        fontWeight: FontWeight.w600,
                                        fontSize: 16,
                                      ),
                                    ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),

                  const SizedBox(height: 16),
                  Center(
                    child: Wrap(
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        const Text("Đã có tài khoản? "),
                        GestureDetector(
                          onTap: () => context.goNamed('login'),
                          child: Text(
                            'Đăng nhập',
                            style: TextStyle(
                              color: colorPrimaryDark,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 18),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
