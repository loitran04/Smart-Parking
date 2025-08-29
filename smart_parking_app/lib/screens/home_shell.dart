import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/user_model.dart';
import '../services/api.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({super.key});
  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  final _pages = const [
    HomeTab(),
    HistoryTab(),
    InfoTab(),
  ];

  @override
Widget build(BuildContext context) {
  const brand = Color(0xFFF24E4E);      // đỏ chủ đạo
  const unselected = Color(0xFF9CA3AF); // xám cho item chưa chọn
  final titles = ['Trang chủ', 'Lịch sử', 'Thông tin cá nhân'];

  return Scaffold(
    appBar: AppBar(
      backgroundColor: Colors.white,
      foregroundColor: brand,
      title: Text(titles[_index], style: const TextStyle(fontWeight: FontWeight.w700)),
      centerTitle: false,
      elevation: 0,
    ),
    body: _pages[_index],

    // <-- Chỉ đổi màu cho thanh dưới của màn hình này
    bottomNavigationBar: NavigationBarTheme(
      data: NavigationBarThemeData(
        backgroundColor: Colors.white,              // nền bar
        indicatorColor: brand.withOpacity(.12),     // “viên thuốc” khi selected
        iconTheme: MaterialStateProperty.resolveWith(
          (states) => IconThemeData(
            color: states.contains(MaterialState.selected) ? brand : unselected,
          ),
        ),
        labelTextStyle: MaterialStateProperty.resolveWith(
          (states) => TextStyle(
            color: states.contains(MaterialState.selected) ? brand : unselected,
            fontWeight: states.contains(MaterialState.selected) ? FontWeight.w600 : FontWeight.w500,
          ),
        ),
      ),
      child: NavigationBar(
        elevation: 0,
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home),
            label: 'Home',
          ),
          NavigationDestination(
            icon: Icon(Icons.history_outlined),     // sửa icon cho đúng History
            selectedIcon: Icon(Icons.history),
            label: 'History',
          ),
          NavigationDestination(
            icon: Icon(Icons.info_outline),
            selectedIcon: Icon(Icons.info),
            label: 'Info',
          ),
        ],
      ),
    ),
  );
}

}

class HomeTab extends StatelessWidget {
  const HomeTab({super.key});

  Future<String> _greet() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString('user_json');
    if (raw == null) return 'Xin chào!';
    final u = UserModel.fromJson(jsonDecode(raw));
    return 'Xin chào, ${u.fullName?.isNotEmpty == true ? u.fullName : u.username} 👋';
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<String>(
      future: _greet(),
      builder: (c, snap) {
        final text = snap.data ?? 'Xin chào!';
        return Center(
          child: Text(
            text,
            style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w600),
          ),
        );
      },
    );
  }
}
class HistoryTab extends StatelessWidget {
  const HistoryTab({super.key});

  Future<String> _greet() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString('user_json');
    if (raw == null) return 'Xin chào!';
    final u = UserModel.fromJson(jsonDecode(raw));
    return 'Xin chào, ${u.fullName?.isNotEmpty == true ? u.fullName : u.username} 👋';
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<String>(
      future: _greet(),
      builder: (c, snap) {
        final text = snap.data ?? 'Xin chào!';
        return Center(
          child: Text(
            text,
            style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w600),
          ),
        );
      },
    );
  }
}
class InfoTab extends StatefulWidget {
  const InfoTab({super.key});
  @override
  State<InfoTab> createState() => _InfoTabState();
}

class _InfoTabState extends State<InfoTab> {
  UserModel? _user;
  bool _loading = false;
  bool _editing = false; // <-- thiếu dòng này

  final _nameC  = TextEditingController();
  final _emailC = TextEditingController();
  final _phoneC = TextEditingController();

  @override
  void initState() {
    super.initState();
    _loadCached();
  }

  @override
  void dispose() {
    _nameC.dispose();
    _emailC.dispose();
    _phoneC.dispose();
    super.dispose();
  }

  Future<void> _loadCached() async {
    final u = await ApiService.getCachedUser();
    setState(() => _user = u);
    if (u != null) {
      _nameC.text  = u.fullName ?? '';
      _emailC.text = u.email ?? '';
      _phoneC.text = u.phone ?? '';
    }
  }

  Future<void> _saveProfile() async {
    setState(() => _loading = true);
    final updated = await ApiService.changeInfo(
      fullName: _nameC.text.trim(),
      email: _emailC.text.trim().isEmpty ? null : _emailC.text.trim(),
      phone: _phoneC.text.trim().isEmpty ? null : _phoneC.text.trim(),
    );
    if (!mounted) return;
    setState(() => _loading = false);

    if (updated != null) {
      setState(() {
        _user = updated;
        _editing = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Đã cập nhật thông tin')),
      );
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Cập nhật thất bại')),
      );
    }
  }

  Future<void> _openChangePasswordDialog() async {
    final oldC = TextEditingController();
    final newC = TextEditingController();
    final repC = TextEditingController();

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Thay đổi mật khẩu'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(obscureText: true, controller: oldC, decoration: const InputDecoration(labelText: 'Mật khẩu hiện tại')),
            TextField(obscureText: true, controller: newC, decoration: const InputDecoration(labelText: 'Mật khẩu mới')),
            TextField(obscureText: true, controller: repC, decoration: const InputDecoration(labelText: 'Nhập lại mật khẩu mới')),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Huỷ')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Đổi')),
        ],
      ),
    );

    if (ok != true) return;
    if (newC.text != repC.text) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Mật khẩu nhập lại không khớp')));
      return;
    }

    final success = await ApiService.changePassword(oldC.text, newC.text);
    if (!mounted) return;
    if (success) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Đổi mật khẩu thành công, vui lòng đăng nhập lại')));
      Navigator.pushReplacementNamed(context, '/login');
    } else {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Đổi mật khẩu thất bại')));
    }
  }

  Future<void> _logout() async {
    await ApiService.logout();
    if (!mounted) return;
    Navigator.pushReplacementNamed(context, '/login');
  }

  @override
  Widget build(BuildContext context) {
    const brand = Color(0xFFF24E4E);
    const brandDark = Color(0xFFE03434);

    if (_user == null && _loading) {
      return const Center(child: CircularProgressIndicator());
    }

    final displayName = _user == null
        ? 'Chưa tải thông tin'
        : (_user!.fullName?.isNotEmpty == true ? _user!.fullName! : _user!.username);

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Row(
          children: [
            const SizedBox(width: 20),
            Expanded(
              child: Text(
                displayName,
                style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w600),
              ),
            ),
            IconButton(
              tooltip: _editing ? 'Huỷ' : 'Sửa thông tin',
              onPressed: () => setState(() => _editing = !_editing),
              icon: Icon(_editing ? Icons.close : Icons.edit),
            )
          ],
        ),
        const SizedBox(height: 16),

        // ----- view / edit block (đã sửa ngoặc)
        if (_editing)
          Card(
            elevation: 0,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                children: [
                  TextFormField(
                    controller: _nameC,
                    decoration: const InputDecoration(
                      prefixIcon: Icon(Icons.badge_outlined),
                      labelText: 'Họ và tên',
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _emailC,
                    keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(
                      prefixIcon: Icon(Icons.mail_outline),
                      labelText: 'Email',
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _phoneC,
                    keyboardType: TextInputType.phone,
                    decoration: const InputDecoration(
                      prefixIcon: Icon(Icons.phone_outlined),
                      labelText: 'SĐT',
                    ),
                  ),
                ],
              ),
            ),
          )
        else
          Card(
            elevation: 0,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            child: Column(
              children: [
                ListTile(
                  leading: const Icon(Icons.account_circle_outlined),
                  title: const Text('Username'),
                  subtitle: Text(_user?.username ?? '—'),
                ),
                const Divider(height: 0),
                ListTile(
                  leading: const Icon(Icons.badge_outlined),
                  title: const Text('Họ và tên'),
                  subtitle: Text(_user?.fullName ?? '—'),
                ),
                const Divider(height: 0),
                ListTile(
                  leading: const Icon(Icons.mail_outline),
                  title: const Text('Email'),
                  subtitle: Text(_user?.email ?? '—'),
                ),
                const Divider(height: 0),
                ListTile(
                  leading: const Icon(Icons.phone_outlined),
                  title: const Text('SĐT'),
                  subtitle: Text(_user?.phone ?? '—'),
                ),
              ],
            ),
          ),

        const SizedBox(height: 16),

        if (_editing)
          FilledButton.icon(
            onPressed: _loading ? null : _saveProfile,
            icon: const Icon(Icons.save_outlined),
            label: const Text('Lưu thay đổi'),
            style: FilledButton.styleFrom(
              backgroundColor: brand, foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
            ),
          )
        else
          FilledButton.tonalIcon(
            onPressed: _openChangePasswordDialog,
            icon: const Icon(Icons.lock_reset),
            label: const Text('Thay đổi mật khẩu'),
            style: FilledButton.styleFrom(
              backgroundColor: brand.withOpacity(.12),
              foregroundColor: brandDark,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
            ),
          ),

        const SizedBox(height: 12),

        FilledButton.icon(
          onPressed: _logout,
          icon: const Icon(Icons.logout),
          label: const Text('Đăng xuất'),
          style: FilledButton.styleFrom(
            backgroundColor: brand,
            foregroundColor: Colors.white,
            overlayColor: brandDark.withOpacity(.12),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
          ),
        ),
      ],
    );
  }
}
