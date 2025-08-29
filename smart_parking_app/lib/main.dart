import 'package:flutter/material.dart';
import 'screens/login.dart';  // Để điều hướng màn hình login
import 'screens/home.dart';  // Màn hình chính sau khi login thành công
import 'screens/register.dart';
import 'screens/home_shell.dart';

void main() {
  runApp(MyApp());
}

class MyApp extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Smart Parking',
      theme: ThemeData(
        primarySwatch: Colors.blue,
        visualDensity: VisualDensity.adaptivePlatformDensity,
      ),
      initialRoute: '/login',
      routes: {
        '/login': (context) => LoginScreen(),
        '/home': (context) => HomeShell(),  // Định nghĩa route cho màn hình home
        '/register': (context) => RegisterScreen(),
        
      },
    );
  }
}
