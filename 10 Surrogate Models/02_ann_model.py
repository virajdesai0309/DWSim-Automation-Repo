"""
02_ann_model.py
===============
Builds, trains, and saves a multi-output Artificial Neural Network (ANN)
that predicts six Heat Exchanger outputs from four inlet conditions.

Framework : PyTorch
Inputs    : cold_inlet_temp, cold_mass_flow, hot_inlet_temp, hot_mass_flow
Outputs   : thermal_efficiency, cold_pressure_drop, hot_pressure_drop,
            global_htc, cold_outlet_temp, hot_outlet_temp

Saved artefacts (in ./ann_artefacts/)
--------------------------------------
  hex_ann_model.pt      – trained model weights
  scaler_X.pkl          – StandardScaler for inputs
  scaler_y.pkl          – StandardScaler for outputs
  training_history.csv  – epoch-level loss log
  training_curves.png   – loss plot
"""

import os
import pickle
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset, random_split
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

# ---------------------------------------------------------------------------
# 0. Config
# ---------------------------------------------------------------------------
DATA_CSV    = "/workspace/10 Surrogate Models/hex_dataset.csv"
ARTEFACT_DIR = "/workspace/10 Surrogate Models/ann_artefacts"
os.makedirs(ARTEFACT_DIR, exist_ok=True)

SEED        = 42
BATCH_SIZE  = 128
EPOCHS      = 500
LR          = 5e-4
HIDDEN      = [256, 512, 256]   # hidden layer widths
DROPOUT     = 0.1
VAL_SPLIT   = 0.15
TEST_SPLIT  = 0.10

torch.manual_seed(SEED)
np.random.seed(SEED)
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Training on: {DEVICE}")

# ---------------------------------------------------------------------------
# 1. Load & validate data
# ---------------------------------------------------------------------------
df = pd.read_csv(DATA_CSV)
print(f"Dataset shape: {df.shape}")

# --- NEW: add derived features ---
df['temp_diff'] = df['hot_inlet_temp'] - df['cold_inlet_temp']
df['flow_product'] = df['cold_mass_flow'] * df['hot_mass_flow']
df['flow_ratio'] = df['cold_mass_flow'] / (df['hot_mass_flow'] + 1e-8)

INPUT_COLS = [
    "cold_inlet_temp", "cold_mass_flow",
    "hot_inlet_temp",  "hot_mass_flow",
    "temp_diff", "flow_product", "flow_ratio"
]
OUTPUT_COLS = ["thermal_efficiency", "cold_pressure_drop", "hot_pressure_drop",
               "global_htc", "cold_outlet_temp", "hot_outlet_temp"]

X_raw = df[INPUT_COLS].values.astype(np.float32)
y_raw = df[OUTPUT_COLS].values.astype(np.float32)

# --- NEW: define which outputs should be log-transformed ---
# Indices of outputs that are strictly positive and span orders of magnitude
LOG_COLS = [1, 2, 3]   # cold_pressure_drop, hot_pressure_drop, global_htc

# Apply log1p to those columns (log(1+x) avoids log(0) if any value is zero)
y_log = y_raw.copy()
for idx in LOG_COLS:
    y_log[:, idx] = np.log1p(y_raw[:, idx])

# Now y_log holds the values we will scale and train on.
# The remaining columns (efficiency, temperatures) are unchanged.

# ---------------------------------------------------------------------------
# 2. Train / Val / Test split (use y_log, not y_raw)
# ---------------------------------------------------------------------------
X_trainval, X_test, y_trainval, y_test = train_test_split(
    X_raw, y_log, test_size=TEST_SPLIT, random_state=SEED)   
X_train, X_val, y_train, y_val = train_test_split(
    X_trainval, y_trainval,
    test_size=VAL_SPLIT / (1 - TEST_SPLIT), random_state=SEED)

print(f"Train: {len(X_train)}  Val: {len(X_val)}  Test: {len(X_test)}")

# ---------------------------------------------------------------------------
# 3. Feature scaling
# ---------------------------------------------------------------------------
scaler_X = StandardScaler()
scaler_y = StandardScaler()

X_train_s = scaler_X.fit_transform(X_train)
X_val_s   = scaler_X.transform(X_val)
X_test_s  = scaler_X.transform(X_test)

y_train_s = scaler_y.fit_transform(y_train)
y_val_s   = scaler_y.transform(y_val)
y_test_s  = scaler_y.transform(y_test)

with open(os.path.join(ARTEFACT_DIR, "scaler_X.pkl"), "wb") as f:
    pickle.dump(scaler_X, f)
with open(os.path.join(ARTEFACT_DIR, "scaler_y.pkl"), "wb") as f:
    pickle.dump(scaler_y, f)

# Also save which outputs were log-transformed (for later inverse transform)
log_info = {"LOG_COLS": LOG_COLS, "OUTPUT_COLS": OUTPUT_COLS}
with open(os.path.join(ARTEFACT_DIR, "log_info.pkl"), "wb") as f:
    pickle.dump(log_info, f)

# Convert to PyTorch tensors
def to_tensor(arr):
    return torch.tensor(arr, dtype=torch.float32)

train_ds = TensorDataset(to_tensor(X_train_s), to_tensor(y_train_s))
val_ds   = TensorDataset(to_tensor(X_val_s),   to_tensor(y_val_s))
test_ds  = TensorDataset(to_tensor(X_test_s),  to_tensor(y_test_s))

train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
val_loader   = DataLoader(val_ds,   batch_size=BATCH_SIZE)
test_loader  = DataLoader(test_ds,  batch_size=BATCH_SIZE)

# ---------------------------------------------------------------------------
# 4. Model definition
# ---------------------------------------------------------------------------
class HEXANN(nn.Module):
    """
    Feed-forward ANN with configurable hidden layers, BatchNorm, and Dropout.
    """
    def __init__(self, n_in: int, n_out: int, hidden: list, dropout: float):
        super().__init__()
        layers = []
        prev = n_in
        for h in hidden:
            layers += [
                nn.Linear(prev, h),
                nn.BatchNorm1d(h),
                nn.SiLU(),
                nn.Dropout(dropout),
            ]
            prev = h
        layers.append(nn.Linear(prev, n_out))
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)


model = HEXANN(
    n_in=len(INPUT_COLS),
    n_out=len(OUTPUT_COLS),
    hidden=HIDDEN,
    dropout=DROPOUT,
).to(DEVICE)

total_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
print(f"Model parameters: {total_params:,}")
print(model)

# ---------------------------------------------------------------------------
# 5. Training
# ---------------------------------------------------------------------------
output_weights = torch.tensor([1.0, 1.0, 2.0, 1.0, 1.0, 1.0]).to(DEVICE)

def weighted_mse_loss(pred, target):
    return (output_weights * (pred - target)**2).mean()

criterion = weighted_mse_loss
optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=1e-5)
scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
    optimizer, mode="min", patience=40, factor=0.5)

history = {"epoch": [], "train_loss": [], "val_loss": []}
best_val_loss = float("inf")
best_state = None
patience = 80
trigger = 0
best_state    = None

for epoch in range(1, EPOCHS + 1):
    # --- training pass ---
    model.train()
    train_loss = 0.0
    for Xb, yb in train_loader:
        Xb, yb = Xb.to(DEVICE), yb.to(DEVICE)
        optimizer.zero_grad()
        pred = model(Xb)
        loss = criterion(pred, yb)
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        train_loss += loss.item() * len(Xb)
    train_loss /= len(train_ds)

    # --- validation pass ---
    model.eval()
    val_loss = 0.0
    with torch.no_grad():
        for Xb, yb in val_loader:
            Xb, yb = Xb.to(DEVICE), yb.to(DEVICE)
            val_loss += criterion(model(Xb), yb).item() * len(Xb)
    val_loss /= len(val_ds)

    scheduler.step(val_loss)

    history["epoch"].append(epoch)
    history["train_loss"].append(train_loss)
    history["val_loss"].append(val_loss)

    # Save best model
    if val_loss < best_val_loss:
        best_val_loss = val_loss
        best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        trigger = 0
    else:
        trigger += 1
        if trigger >= patience:
            print(f"Early stopping at epoch {epoch}")
            break
        
    if epoch % 10 == 0 or epoch == 1:
        print(f"Epoch {epoch:4d}/{EPOCHS}  Train MSE: {train_loss:.6f}  Val MSE: {val_loss:.6f}")

# ---------------------------------------------------------------------------
# 6. Save model & training history
# ---------------------------------------------------------------------------
model.load_state_dict(best_state)
torch.save({
    "model_state":  model.state_dict(),
    "model_config": {"n_in": len(INPUT_COLS),
                     "n_out": len(OUTPUT_COLS),
                     "hidden": HIDDEN,
                     "dropout": DROPOUT},
    "input_cols":  INPUT_COLS,
    "output_cols": OUTPUT_COLS,
    "log_info": log_info,
}, os.path.join(ARTEFACT_DIR, "hex_ann_model.pt"))

pd.DataFrame(history).to_csv(
    os.path.join(ARTEFACT_DIR, "training_history.csv"), index=False)

# ---------------------------------------------------------------------------
# 7. Evaluate on held-out test set
# ---------------------------------------------------------------------------
model.eval()
all_pred, all_true = [], []
with torch.no_grad():
    for Xb, yb in test_loader:
        all_pred.append(model(Xb.to(DEVICE)).cpu().numpy())
        all_true.append(yb.numpy())

y_pred_s = np.vstack(all_pred)
y_true_s = np.vstack(all_true)

# Inverse transform from scaled space to log-transformed space
y_pred_log = scaler_y.inverse_transform(y_pred_s)
y_true_log = scaler_y.inverse_transform(y_true_s)

# Convert from log space back to physical units (only for LOG_COLS)
y_pred = y_pred_log.copy()
y_true = y_true_log.copy()
for idx in LOG_COLS:
    y_pred[:, idx] = np.expm1(y_pred_log[:, idx])
    y_true[:, idx] = np.expm1(y_true_log[:, idx])

mae  = np.abs(y_pred - y_true).mean(axis=0)
rmse = np.sqrt(((y_pred - y_true) ** 2).mean(axis=0))
r2   = 1 - ((y_true - y_pred)**2).sum(axis=0) / ((y_true - y_true.mean(axis=0))**2).sum(axis=0)

print("\n--- Test-set metrics (physical units) ---")
header = f"{'Output':<25} {'MAE':>12} {'RMSE':>12} {'R²':>8}"
print(header)
print("-" * len(header))
for col, m, r, r2v in zip(OUTPUT_COLS, mae, rmse, r2):
    print(f"{col:<25} {m:12.4f} {r:12.4f} {r2v:8.4f}")

# ---------------------------------------------------------------------------
# 8. Training curves
# ---------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(9, 4))
ax.semilogy(history["epoch"], history["train_loss"], label="Train MSE")
ax.semilogy(history["epoch"], history["val_loss"],   label="Val MSE")
ax.set_xlabel("Epoch")
ax.set_ylabel("MSE (scaled units)")
ax.set_title("HEX-ANN Training History")
ax.legend()
ax.grid(True, which="both", linestyle="--", alpha=0.5)
plt.tight_layout()
plt.savefig(os.path.join(ARTEFACT_DIR, "training_curves.png"), dpi=150)
print(f"\nTraining curves saved → {ARTEFACT_DIR}/training_curves.png")
print(f"Model saved → {ARTEFACT_DIR}/hex_ann_model.pt")