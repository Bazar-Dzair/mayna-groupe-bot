إصلاح خطأ No module named playwright

سبب الخطأ: ملف requirements.txt الموجود في مستودع GitHub لا يحتوي على مكتبة playwright، لذلك فشل الأمر python -m playwright install.

ضع الملف requirements.txt في جذر مستودع البوت (نفس مستوى bot.py)، واستبدل الملف القديم به، ثم Commit changes وأعد تشغيل GitHub Actions.

تأكد كذلك أن ملف .github/workflows/bot.yml يحتوي على:
  pip install -r requirements.txt
  python -m playwright install --with-deps chromium

ملاحظة: هذا يصلح خطأ تثبيت المكتبة فقط، ولا يضمن أن استخراج حالة DHD سينجح قبل اختبار الموقع.
