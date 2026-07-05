#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import pandas as pd
import numpy as np

class PerformanceDeviationAnalyzer:
    def __init__(self, db_path='task_performance_data.db', actual_user='anpeirong'):
        self.db_path = db_path
        self.actual_user = actual_user
        self.tolerance_levels = ['high', 'low']
        
        self.table_metrics = {
            'threat_task_performance_nonAI': ['更新最具威胁项准确率', '临机事件响应时长_秒'],
            'sensor_task_performance_nonAI': ['雷达初始设置耗时_毫秒', '雷达参数调节耗时_秒', '目标锁定耗时_秒', '目标锁定准确率'],
            'platform_task_performance_nonAI': ['目标路径点完成比例', '目标路径点完成耗时_秒', '目标路径点完成精度'],
            'weapon_task_performance_nonAI': ['目标击中成功率', '发射武器平均耗时_秒'],
            'sensor_task_performance_AI': ['智能助手完成目标锁定平均时长', '操作员完成目标锁定平均时长', '智能助手目标锁定准确率', '操作员目标锁定准确率'],
            'platform_task_performance_AI': ['智能助手路径点完成比例', '操作员路径点完成比例', '智能助手路径点完成平均时间', '操作员路径点完成平均时间', '智能助手路径点完成平均精度', '操作员路径点完成平均精度'],
            'threat_task_performance_AI': ['智能助手临机事件响应时长', '操作员临机事件响应时长', '智能助手更新最具威胁项准确率', '操作员更新最具威胁项准确率'],
            'weapon_task_performance_AI': ['操作员目标击中成功率', '发射武器平均耗时_秒']
        }
        
    def get_table_names(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [table[0] for table in cursor.fetchall()]
        conn.close()
        return tables
    
    def load_data_from_table(self, table_name):
        conn = sqlite3.connect(self.db_path)
        query = f"SELECT * FROM {table_name}"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    
    def calculate_deviation_for_table(self, table_name):
        print(f"正在分析表: {table_name}")
        
        if table_name not in self.table_metrics:
            print(f"警告: 表 {table_name} 没有定义绩效指标")
            return None
            
        performance_metrics = self.table_metrics[table_name]
        df = self.load_data_from_table(table_name)
        
        actual_data = df[df['用户名'] == self.actual_user].copy()
        experimental_data = df[df['用户名'] != self.actual_user].copy()
        
        if actual_data.empty:
            print(f"警告: 表 {table_name} 中没有找到用户 {self.actual_user} 的数据")
            return None
            
        if experimental_data.empty:
            print(f"警告: 表 {table_name} 中没有找到其他用户的数据")
            return None
        
        actual_users = actual_data['用户名'].unique().tolist()
        experimental_users = experimental_data['用户名'].unique().tolist()
        
        results = {
            'table_name': table_name,
            'actual_user': self.actual_user,
            'actual_users_used': actual_users,
            'experimental_users_used': experimental_users,
            'actual_count': len(actual_data),
            'experimental_count': len(experimental_data),
            'average_relative_deviation': 0.0
        }
        
        relative_deviations = []
        
        for metric in performance_metrics:
            if metric not in actual_data.columns:
                print(f"警告: 指标 {metric} 在表 {table_name} 中不存在")
                continue
                
            actual_values = actual_data[metric].dropna().values
            experimental_values = experimental_data[metric].dropna().values
            
            if len(actual_values) == 0 or len(experimental_values) == 0:
                print(f"警告: 指标 {metric} 没有有效数据")
                continue
            
            actual_mean = np.mean(actual_values)
            experimental_mean = np.mean(experimental_values)
            mean_deviation = actual_mean - experimental_mean
            
            if experimental_mean != 0:
                relative_deviation = (mean_deviation / experimental_mean) * 100
                relative_deviations.append(relative_deviation)
            else:
                print(f"警告: 指标 {metric} 的等效实验均值为0，跳过")
        
        if relative_deviations:
            results['average_relative_deviation'] = float(np.mean(relative_deviations))
        else:
            print(f"警告: 表 {table_name} 没有有效的相对偏差数据")
            results['average_relative_deviation'] = 0.0
        
        return results
    
    def analyze_all_tables(self):
        table_names = self.get_table_names()
        all_results = {}
        
        print(f"开始分析 {len(table_names)} 个表...")
        
        for table_name in table_names:
            try:
                result = self.calculate_deviation_for_table(table_name)
                if result:
                    all_results[table_name] = result
            except Exception as e:
                print(f"分析表 {table_name} 时出错: {e}")
                continue
        
        return all_results
    
    def print_summary(self, results):
        print("\n" + "="*80)
        print("绩效相对偏差分析结果")
        print("="*80)
        
        if results:
            first_result = list(results.values())[0]
            experimental_users = first_result['experimental_users_used']
            actual_user = first_result['actual_user']
            print(f"实际场景用户: {actual_user}")
            print(f"等效实验用户: {', '.join(experimental_users)}")
        
        nonai_tasks = []
        ai_tasks = []
        nonai_task_names = []
        ai_task_names = []
        
        for table_name, result in results.items():
            if 'nonAI' in table_name:
                nonai_tasks.append(result['average_relative_deviation'])
                nonai_task_names.append(table_name)
            elif 'AI' in table_name:
                ai_tasks.append(result['average_relative_deviation'])
                ai_task_names.append(table_name)
        
        if nonai_tasks:
            nonai_average = np.mean(nonai_tasks)
            print(f"\n交互等效任务平均偏差: {nonai_average:.2f}%")
            print(f"  包含任务: {len(nonai_tasks)}个")
            print(f"  任务列表: {', '.join(nonai_task_names)}")
        else:
            print("\n交互等效任务: 无数据")
            
        if ai_tasks:
            ai_average = np.mean(ai_tasks)
            print(f"\n信任等效任务平均偏差: {ai_average:.2f}%")
            print(f"  包含任务: {len(ai_tasks)}个")
            print(f"  任务列表: {', '.join(ai_task_names)}")
        else:
            print("\n信任等效任务: 无数据")

def main():
    ACTUAL_USER = 'anpeirong' 
    
    print(f"绩效相对偏差分析开始...")
    print(f"实际场景用户: {ACTUAL_USER}")
    print(f"等效实验用户: 其他所有用户")
    
    analyzer = PerformanceDeviationAnalyzer(actual_user=ACTUAL_USER)
    results = analyzer.analyze_all_tables()
    
    if not results:
        print("没有找到有效的分析结果")
        return
    
    analyzer.print_summary(results)
    print(f"\n分析完成！")

if __name__ == "__main__":
    main()
