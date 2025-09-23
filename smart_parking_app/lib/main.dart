import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'screens/login.dart';
import 'screens/register.dart';
import 'screens/shell/home_shell.dart';
import 'screens/tabs/home_tab.dart';
import 'screens/tabs/history_tab.dart';
import 'screens/tabs/info_tab.dart';
import 'screens/receipt/reservation_receipt.dart';
import 'admin/admin_shell.dart';
import 'screens/payment_history_page.dart';

final GoRouter appRouter = GoRouter(
  initialLocation: '/login', 
  debugLogDiagnostics: true, 
  routes: <RouteBase>[
    GoRoute(
      path: '/login',
      name: 'login',
      builder: (context, state) => const LoginScreen(),
    ),
    GoRoute(
      path: '/admin',
      name: 'admin',
      builder: (context, state) => AdminShell(),
    ),
    GoRoute(
      path: '/register', 
      name: 'register',
      builder: (context, state) => const RegisterScreen(),
    ),
    ShellRoute(
      builder: (context, state, child) =>
          HomeShell(child: child, location: state.uri.path),
      routes: <RouteBase>[
        GoRoute(
          path: '/home',
          name: 'home',
          builder: (_, __) => const HomeTab(),
        ),
        GoRoute(
          path: '/history',
          name: 'history',
          builder: (_, __) => const HistoryTab(),
        ),
        GoRoute(
          path: '/info',
          name: 'info',
          builder: (_, __) => const InfoTab(),
        ),
        GoRoute(
          path: '/payments',
          name: 'payments',
          builder: (_, __) => const PaymentHistoryPage(),
        ),

      ],
    ),
    GoRoute(
      path: '/reservation/:id',
      name: 'receipt',
      builder: (context, state) {
        final id = state.pathParameters['id']!;
        final extra = state.extra; 
        return ReservationReceiptScreen(reservationId: id, initial: extra);
      },
    ),
  ],
);

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  Intl.defaultLocale = 'vi'; 
  await initializeDateFormatting(
    'vi',
  ); 
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});
  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      routerConfig: appRouter,
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFFF24E4E)),
      ),
      supportedLocales: const [Locale('vi'), Locale('en')],
    );
  }
}
