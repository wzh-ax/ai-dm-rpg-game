# -*- coding: utf-8 -*-
"""
体验官脚本 v3 - 使用 subprocess 管道运行交互式游戏
"""
import asyncio
import subprocess
import sys
import os
import time
from datetime import datetime
from typing import Optional

# 游戏入口
GAME_PATH = r"D:\ai-dm-rpg-game\interactive_master.py"

class AutoPlayer:
    def __init__(self):
        self.proc: Optional[subprocess.Popen] = None
        self.output_lines = []
        self.start_time = None
        self.turn_count = 0
        
    def start(self):
        """启动游戏进程"""
        print("启动游戏进程...")
        self.proc = subprocess.Popen(
            [sys.executable, GAME_PATH],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding='utf-8',
            errors='replace',
            bufsize=1,
            cwd=os.path.dirname(GAME_PATH)
        )
        self.start_time = datetime.now()
        
    def send(self, text: str):
        """发送输入"""
        if self.proc and self.proc.stdin:
            self.proc.stdin.write(text + "\n")
            self.proc.stdin.flush()
            self.turn_count += 1
            print(f"[输入 {self.turn_count}] {text}")
            
    def read_output(self, timeout=2.0) -> str:
        """读取输出（带超时）"""
        if not self.proc:
            return ""
        
        output = []
        try:
            while True:
                line = self.proc.stdout.readline()
                if not line:
                    break
                output.append(line)
                if line.strip().endswith("📜 > "):
                    break
        except:
            pass
        return "".join(output)
    
    def play_sequence(self):
        """执行游戏序列"""
        # 等待启动
        time.sleep(1)
        initial = self.read_output(timeout=3)
        self.output_lines.append(initial)
        print(f"[启动输出 {len(initial)} 字符]")
        
        # 选择: new (开始游戏)
        self.send("new")
        time.sleep(0.5)
        out = self.read_output(timeout=2)
        self.output_lines.append(out)
        
        # 输入角色名
        self.send("体验官")
        time.sleep(0.3)
        
        # 选择种族: 1 (人类)
        self.send("1")
        time.sleep(0.3)
        
        # 选择职业: 1 (战士)
        self.send("1")
        time.sleep(0.3)
        
        # 确认创建
        self.send("yes")
        time.sleep(1)
        
        out = self.read_output(timeout=5)
        self.output_lines.append(out)
        print(f"[角色创建完成]")
        
        # 游戏序列
        game_inputs = [
            "我走进酒馆，环顾四周",
            "去镇中心看看",
            "和周围的人说话",
            "去酒馆找个位置坐下",
            "我突然想跳舞，在酒馆中央跳了起来",
            "离开酒馆，去外面的街道走走",
            "去市场逛逛",
            "去镇子外面的森林冒险",
        ]
        
        for action in game_inputs:
            self.send(action)
            time.sleep(3)  # 等待 LLM 处理
            out = self.read_output(timeout=5)
            self.output_lines.append(out)
            print(f"[{action[:15]}...] 获得 {len(out)} 字符输出")
        
        # 发送quit
        self.send("quit")
        time.sleep(1)
        
    def close(self):
        """关闭进程"""
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except:
                self.proc.kill()
    
    def get_full_output(self) -> str:
        return "\n".join(self.output_lines)
    
    def get_duration(self) -> float:
        if self.start_time:
            return (datetime.now() - self.start_time).total_seconds()
        return 0


async def main():
    player = AutoPlayer()
    try:
        player.start()
        player.play_sequence()
    except Exception as e:
        print(f"执行出错: {e}")
    finally:
        player.close()
    
    duration = player.get_duration()
    full_output = player.get_full_output()
    
    # 保存输出
    output_file = r"D:\ai-dm-rpg-game\tests\experience_raw_output.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(full_output)
    
    print(f"\n游戏执行完成!")
    print(f"时长: {duration:.1f}秒")
    print(f"回合数: {player.turn_count}")
    print(f"输出已保存到: {output_file}")
    
    return full_output


if __name__ == "__main__":
    output = asyncio.run(main())
