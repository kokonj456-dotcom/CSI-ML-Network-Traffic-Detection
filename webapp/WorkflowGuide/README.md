# Flowwatch Workflow Guide

เปิด index.html ในเบราว์เซอร์เพื่ออ่านแผนภาพและซอร์สจากเครื่องนี้ เว็บอ่านข้อมูลจาก catalog.js ที่สร้างจาก repo และเปิดได้โดยไม่ต้องรัน Dashboard หรือ MySQL

เมื่อแก้โค้ด ให้รันจากโฟลเดอร์หลักของ repo

    python webapp/WorkflowGuide/build_catalog.py

ตัวสร้างใช้ Python 3.10 ขึ้นไป, Git, Node และ Babel parser ที่ติดตั้งมากับ Dashboard frontend หากยังไม่มี node_modules ให้ติดตั้ง dependencies ใน Dashboard frontend ด้วย npm ci ก่อน

สารบัญครอบคลุม Dashboard (frontend และ backend) กับ Traffic Replay และอ่านเฉพาะไฟล์ในสองส่วนนี้ที่ Git ติดตามหรือยังไม่ได้ ignore และแสดงไฟล์ข้อมูลหรือไฟล์โมเดลเป็นชื่อกับตำแหน่ง ไฟล์ .env จริงและซอร์สที่ใหญ่เกิน 1 MB จะไม่ถูกคัดลอก ส่วน notebook แสดงซอร์สจาก code cells โดยอ้างอิงบรรทัดในซอร์สที่รวมแล้ว

คำอธิบายบางฟังก์ชันเขียนให้ตามงานจริง ส่วนรายการทั่วไปใช้ docstring และรายการขั้นตอนที่สกัดจากซอร์ส ลิงก์การเรียกฟังก์ชันแสดงเมื่อค้นเจอปลายทางที่ชัดเจนจากชื่อและ import ส่วนการเชื่อมข้าม HTTP ดูจากแผนภาพด้านบน
