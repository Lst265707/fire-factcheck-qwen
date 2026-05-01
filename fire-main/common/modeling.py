import re
import dashscope
import os
from common import utils

# ====================== 【提示词】 =====================================
SYS_PROMPT = '''你是一个自动化事实核查智能体，专门执行**虚假新闻检测的二分类任务**。
对于给定的新闻文本，你需要基于事实准确性判断其为真实新闻或虚假新闻，
**只允许输出：真实 / 虚假**，不输出任何多余内容、解释或推理过程。
'''
# ======================================================================
#定义模型
class Model:
    def __init__(
            self,
            model_name: str,
            temperature: float = 0.5,
            max_tokens: int = 2048,
            show_responses: bool = False,
            show_prompts: bool = False,
    ) -> None:
        self.organization, self.model_id = model_name.split(':')
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.show_responses = show_responses
        self.show_prompts = show_prompts
        self.model = self.load_model()

    def load_model(self):
        if self.organization == 'qwen':
            return "qwen-native"
        else:
            raise ValueError(f"Unsupported organization: {self.organization}")

    # ====================== 【自动转 JSON，永不报错】 ======================
    def _to_json(self, text: str) -> str:
        clean = text.strip().upper()
        if "真实" in clean or "TRUE" in clean or "True" in clean:
            return '{"final_answer": "True"}'
        if "虚假" in clean or "FALSE" in clean or "False" in clean:
            return '{"final_answer": "False"}'

        # 兜底
        return '{"final_answer": "True"}'

    def generate(self, context: str) -> tuple[str, dict | None]:
        if self.organization == 'qwen':
            return self._generate_qwen_native(context)
        else:
            raise ValueError(f"Unsupported organization: {self.organization}")

    def _generate_qwen_native(self, context: str):
        import os
        import dashscope

        dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")

        messages = [
            {"role": "system", "content": SYS_PROMPT},
            {"role": "user", "content": context}
        ]

        resp = dashscope.Generation.call(
            model=self.model_id,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            result_format="message"
        )

        content = resp.output.choices[0].message.content
        # 自动转成框架需要的 JSON
        final_json = self._to_json(content)

        usage = {
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens
        }

        print(f"✅ Qwen输出: {content.strip()} → 转为JSON: {final_json}")
        return final_json, usage

    def print_config(self) -> None:
        settings = {
            'organization': self.organization,
            'model_id': self.model_id,
            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
            'show_responses': self.show_responses,
            'show_prompts': self.show_prompts,
        }
        print(utils.to_readable_json(settings))