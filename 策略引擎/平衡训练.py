#!/usr/bin/env python3
import pandas as pd, numpy as np, warnings, os, sys
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score, confusion_matrix
import lightgbm as lgb

# Load existing samples
样本 = pd.read_csv('10_实验记录/lightgbm_样本_20260719_174453.csv')
print(f'加载样本: {len(样本)} 笔')
print(f'真突破: {样本["label"].sum()} ({样本["label"].sum()/len(样本)*100:.1f}%)')
print(f'假突破: {len(样本)-样本["label"].sum()} ({(1-样本["label"].sum()/len(样本))*100:.1f}%)')

特征列 = [c for c in 样本.columns if c not in ('label', '股票')]
X = 样本[特征列].values
y = 样本['label'].values

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

# scale_pos_weight
pos_w = (len(y_train) - y_train.sum()) / y_train.sum()
print(f'scale_pos_weight: {pos_w:.1f}')

params = {
    'objective': 'binary',
    'metric': 'auc',
    'boosting_type': 'gbdt',
    'num_leaves': 31,
    'learning_rate': 0.05,
    'feature_fraction': 0.8,
    'bagging_fraction': 0.8,
    'bagging_freq': 5,
    'verbose': -1,
    'random_state': 42,
    'min_data_in_leaf': 10,
    'scale_pos_weight': pos_w,
}

train_data = lgb.Dataset(X_train, label=y_train, feature_name=特征列)
test_data = lgb.Dataset(X_test, label=y_test, reference=train_data)

model = lgb.train(
    params, train_data,
    valid_sets=[test_data],
    num_boost_round=300,
    callbacks=[lgb.early_stopping(30), lgb.log_evaluation(0)]
)

y_prob = model.predict(X_test)
y_pred = (y_prob > 0.5).astype(int)
y_pred_4 = (y_prob > 0.4).astype(int)
y_pred_6 = (y_prob > 0.6).astype(int)

S = '=' * 50
print(f'\n{S}')
print('平衡训练结果')
print(S)

print(f'\n阈值=0.5:')
print(f'  准确率: {accuracy_score(y_test, y_pred):.3f}')
print(f'  精确率: {precision_score(y_test, y_pred):.3f}')
print(f'  召回率: {recall_score(y_test, y_pred):.3f}')
print(f'  AUC:   {roc_auc_score(y_test, y_prob):.3f}')
cm = confusion_matrix(y_test, y_pred)
print(f'  TP={cm[1][1]} FP={cm[0][1]} FN={cm[1][0]} TN={cm[0][0]}')

print(f'\n阈值=0.4:')
print(f'  精确率: {precision_score(y_test, y_pred_4):.3f}')
print(f'  召回率: {recall_score(y_test, y_pred_4):.3f}')

print(f'\n阈值=0.6:')
print(f'  精确率: {precision_score(y_test, y_pred_6):.3f}')
print(f'  召回率: {recall_score(y_test, y_pred_6):.3f}')

probs = y_prob
print(f'\n概率分布:')
print(f'  <0.3: {(probs<0.3).sum()} ({((probs<0.3).sum()/len(probs)*100):.0f}%)')
print(f'  0.3-0.6: {((probs>=0.3)&(probs<=0.6)).sum()} ({(probs>=0.3)&(probs<=0.6).sum()/len(probs)*100:.0f}%)')
print(f'  >0.6: {(probs>0.6).sum()} ({(probs>0.6).sum()/len(probs)*100:.0f}%)')

# Feature importance
重要性 = pd.DataFrame({
    '特征': 特征列,
    '重要性': model.feature_importance(importance_type='gain')
}).sort_values('重要性', ascending=False)
print(f'\n特征重要性:')
for _, r in 重要性.iterrows():
    print(f'  {r["特征"]}: {r["重要性"]:.0f}')

# Save model
时间戳 = datetime.now().strftime('%Y%m%d_%H%M%S')
模型路径 = f'10_实验记录/lightgbm_平衡模型_{时间戳}.txt'
model.save_model(模型路径)
print(f'\n平衡模型已保存: {模型路径}')

print(f'\n原模型对比:')
print(f'  原模型(AUC=0.910):  <0.3占98%, 召回率1.6%')
print(f'  平衡模型:           <0.3占{(probs<0.3).sum()/len(probs)*100:.0f}%, 召回率{recall_score(y_test, y_pred):.1%}')
