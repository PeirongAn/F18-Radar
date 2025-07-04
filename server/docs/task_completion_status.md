# 任务完成状态管理说明

## 概述

任务完成状态管理功能通过 `is_completed` 字段跟踪用户任务的生命周期，确保系统能够准确识别任务的当前状态。

## 状态含义

- `is_completed = TRUE`: 任务已完成
- `is_completed = FALSE`: 任务未完成/进行中

## 状态检查流程

### 1. 获取新任务前的状态检查

在 `get_next_task_parameters()` 方法中，系统会：

1. **检查上一个任务状态**: 调用 `_check_previous_task_completion_status()`
2. **判断是否需要状态更新**: 根据当前任务状态决定下一步操作
3. **更新状态**: 在适当的时机更新 `is_completed` 字段

### 2. 状态检查逻辑

```python
def _check_previous_task_completion_status(self) -> bool:
    """
    Returns:
        True: 上一个任务已完成（可以开始新任务）
        False: 上一个任务仍在进行中
    """
```

#### 练习模式
- 检查内存缓存中的 `is_completed` 值
- 没有缓存记录视为已完成

#### 正式模式  
- 查询数据库中的 `is_completed` 值
- 没有数据库记录视为已完成

## 状态变更时机

### 设置为 FALSE (任务未完成/进行中)

1. **新场景开始时**
   ```python
   self.current_scenario = self.active_queue.pop(0)
   self._update_completion_status(False)  # 新任务开始，设为未完成
   ```

2. **首次获取任务时**
   - 用户首次请求任务参数时

### 设置为 TRUE (任务已完成)

1. **场景重复次数达到上限**
   ```python
   if self.repetition_counter >= self.max_repetitions:
       self._update_completion_status(True)  # 当前场景完成
   ```

2. **切换任务模式时**
   ```python
   if queue_switched and self.current_scenario:
       self._update_completion_status(True)  # 切换前标记完成
   ```

3. **队列为空时**
   ```python
   if not self.current_scenario:
       self._update_completion_status(True)  # 没有更多任务
   ```

4. **手动标记完成**
   ```python
   task_manager.mark_task_completed()  # 外部调用
   ```

## 使用场景

### 1. 任务恢复

当用户重新进入系统时，系统可以通过 `is_completed` 状态判断：
- 是否有未完成的任务
- 是否需要恢复任务进度
- 是否可以开始新任务

### 2. 并发控制

防止用户同时进行多个任务：
- 检查是否有进行中的任务
- 确保任务的唯一性和一致性

### 3. 数据统计

在数据分析时：
- 识别完整的任务周期
- 统计任务完成率
- 分析用户行为模式

## 错误处理

### 数据库连接失败
```python
except Exception as e:
    self.logger.error(f"Error checking previous task completion status: {e}")
    return True  # 默认视为已完成，允许继续操作
```

### 状态不一致处理
- 系统优先保证功能可用性
- 记录详细日志便于问题排查
- 提供手动修复接口

## 测试验证

使用 `server/test_task_completion.py` 可以验证：

1. **状态创建**: 新任务时状态正确设置
2. **状态更新**: 不同场景下状态正确变更  
3. **状态检查**: 获取任务前正确检查状态
4. **模式切换**: 练习模式和正式模式状态管理
5. **错误处理**: 异常情况下的状态处理

## 最佳实践

### 1. 状态检查
在获取新任务前，始终检查上一个任务状态：
```python
previous_task_completed = self._check_previous_task_completion_status()
if not previous_task_completed:
    self.logger.warning("Previous task still in progress")
```

### 2. 显式状态管理
在关键节点显式更新状态：
```python
# 任务开始
self._update_completion_status(False)  # 未完成/进行中

# 任务结束
self._update_completion_status(True)   # 已完成
```

### 3. 日志记录
记录所有状态变更：
```python
self.logger.info(f"Task status changed: is_completed={is_active}")
```

## 监控建议

### 数据库查询
```sql
-- 检查进行中的任务
SELECT user_id, task_type, last_updated 
FROM user_progress 
WHERE is_completed = FALSE;

-- 统计任务完成情况
SELECT 
    COUNT(*) as total_tasks,
    SUM(CASE WHEN is_completed = FALSE THEN 1 ELSE 0 END) as active_tasks,
    SUM(CASE WHEN is_completed = TRUE THEN 1 ELSE 0 END) as completed_tasks
FROM user_progress;
```

### 日志监控
关注以下日志模式：
- `Task status changed`
- `Previous task completion status`
- `Mode switched, marking previous task as completed`
- `Current scenario repetitions completed` 