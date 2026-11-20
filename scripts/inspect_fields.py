import inspect
from core.code_executor import CodeExecutor
from core.prompts import prepare_prompt

print(inspect.getsource(CodeExecutor._build_runner_script))
print("\n" + "=" * 60 + "\n")
print(inspect.getsource(prepare_prompt)[-1500:])