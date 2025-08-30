import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'screens/login.dart';
import 'screens/register.dart';
import 'screens/shell/home_shell.dart';
import 'screens/tabs/home_tab.dart';
import 'screens/tabs/history_tab.dart';
import 'screens/tabs/info_tab.dart';

final GoRouter appRouter = GoRouter(
  initialLocation: '/login',                 // vào login trước cho rõ ràng
  debugLogDiagnostics: true,                 // in ra cây route để kiểm tra
  routes: <RouteBase>[
    GoRoute(
      path: '/login',
      name: 'login',
      builder: (context, state) => const LoginScreen(),
    ),
    GoRoute(
      path: '/register',                     // << BẮT BUỘC có
      name: 'register',
      builder: (context, state) => const RegisterScreen(),
    ),
    ShellRoute(
      builder: (context, state, child) =>
          HomeShell(child: child, location: state.uri.path),
      routes: <RouteBase>[
        GoRoute(path: '/home',    name: 'home',    builder: (_, __) => const HomeTab()),
        GoRoute(path: '/history', name: 'history', builder: (_, __) => const HistoryTab()),
        GoRoute(path: '/info',    name: 'info',    builder: (_, __) => const InfoTab()),
      ],
    ),
  ],
);

void main() => runApp(const MyApp());

class MyApp extends StatelessWidget {
  const MyApp({super.key});
  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      routerConfig: appRouter,               // dùng đúng router này
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFFF24E4E)),
      ),
    );
  }
}
