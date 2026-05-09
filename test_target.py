"""test_target.py —— 用于测试 Code Review 系统的示例文件

包含故意设计的问题：硬编码密钥、裸 except、f-string SQL 拼接、etc。
"""

import os
import sqlite3

API_KEY = "sk-abc123def456ghi789"   # 安全风险：硬编码密钥


class UserManager:
    """用户管理类"""

    def __init__(self, db_path):
        self.db_path = db_path

    def get_user(self, user_id):
        """根据ID获取用户——存在SQL注入风险。"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        # 问题：f-string SQL拼接
        cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
        result = cursor.fetchone()
        conn.close()
        return result

    def get_user_safe(self, user_id):
        """参数化查询的安全版本。"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result

    def list_users(self):
        """列出所有用户。"""
        users = []
        for i in range(10000):
            try:
                user = self.get_user(i)
                if user:
                    users.append(user)
            except:     # 问题：裸 except，吞掉所有异常
                pass
        return users

    def process_data(self, data):
        """处理数据——存在性能问题。"""
        result = ""
        for item in data:      # 性能问题：循环内字符串 += 拼接
            result += str(item) + ", "
        return result[:-2]


def dangerous_function(user_input):
    """危险函数——使用eval执行用户输入。"""
    return eval(user_input)   # 安全风险：eval()


def calculate_average(numbers):
    """计算平均值。"""
    total = 0
    count = 0
    for n in numbers:
        total = total + n
        count = count + 1
    if count == 0:
        return 0
    return total / count


# 性能问题：循环中的I/O操作
def log_messages(messages):
    for msg in messages:
        with open("app.log", "a") as f:
            f.write(msg + "\n")


if __name__ == "__main__":
    print(calculate_average([1, 2, 3, 4, 5]))
