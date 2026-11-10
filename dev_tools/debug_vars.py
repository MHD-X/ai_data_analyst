"""اختبار سريع: هل يُصدَّر المتغيرات من الـ sandbox؟"""
from core.code_executor import get_executor

# ---------- اختبار 1: بدون بيانات ----------
print("=" * 60)
print("اختبار 1: متغيرات بسيطة بدون ملف بيانات")
print("=" * 60)

code1 = """
my_var = 42
my_str = 'hello'
my_list = [1, 2, 3]
"""
r1 = get_executor().execute(code1)
print("success  :", r1.success)
print("variables:", r1.variables)
print("stdout   :", repr(r1.stdout))
print("stderr   :", repr(r1.stderr[:300] if r1.stderr else ""))


# ---------- اختبار 2: مع ملف بيانات ----------
print()
print("=" * 60)
print("اختبار 2: مع ملف بيانات + df")
print("=" * 60)

import pandas as pd
from pathlib import Path

p = Path("data/uploads/__debug2__.csv")
p.parent.mkdir(parents=True, exist_ok=True)
pd.DataFrame({"x": [1, 2, 3]}).to_csv(p, index=False)

code2 = """
print(df.shape)
result = df['x'].sum()
print('sum:', result)
"""
r2 = get_executor().execute(code2, data_path=str(p))
print("success  :", r2.success)
print("variables:", r2.variables)
print("stdout   :", repr(r2.stdout))
print("stderr   :", repr(r2.stderr[:300] if r2.stderr else ""))

p.unlink(missing_ok=True)


# ---------- اختبار 3: عرض السكربت المُولَّد ----------
print()
print("=" * 60)
print("اختبار 3: عرض السكربت المُولَّد (آخر 60 سطراً)")
print("=" * 60)

executor = get_executor()
script = executor._build_runner_script(code1, None)
lines = script.split("\n")
print("\n".join(lines[-60:]))