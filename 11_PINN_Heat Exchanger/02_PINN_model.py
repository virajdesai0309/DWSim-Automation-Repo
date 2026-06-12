"""
02_hex_pinn.py
==============
Physics-Informed Neural Network (PINN) for a Shell-and-Tube Heat Exchanger.
Tuned for the 30,000-point dataset.

Governing ODEs (counter-current, 1-D steady-state energy balance)
------------------------------------------------------------------
Hot side  :  ṁ_h · Cp · dT_h/dξ = -U · A_total · (T_h - T_c)
Cold side :  ṁ_c · Cp · dT_c/dξ = -U · A_total · (T_h - T_c)

where ξ ∈ [0, 1] is the normalised axial coordinate (x / L).

Counter-current convention
--------------------------
Hot  fluid : enters at ξ=0, exits at ξ=1
Cold fluid : enters at ξ=1, exits at ξ=0
Both ODEs share the same sign because both T_h and T_c decrease
in their respective flow directions across the exchanger.

Network
-------
Input  : [ξ, cold_inlet_temp, hot_inlet_temp, cold_mass_flow, hot_mass_flow, global_htc]
Output : [T_h(ξ),  T_c(ξ)]   (scaled temperatures)

Loss
----
  L_total = w_data · L_data  +  w_phys · L_phys  +  w_bc · L_bc

Training phases
---------------
  Phase 1 — Data only       (epochs   0 – 1499) : warm-start weights
  Phase 2 — Physics ramp    (epochs 1500 – 2999) : linearly ramp w_phys 0 → w_phys
  Phase 3 — Full joint      (epochs 3000 – 8000) : Adam fine-tune all losses
  Phase 4 — L-BFGS polish   (up to 500 steps)    : final convergence

Device-adaptive defaults
------------------------
  CPU (current) : 4 layers × 64 neurons, 2000 epochs, batch 512, n_colloc 500
                  → ~60-90 min on a modern CPU
  GPU (future)  : 6 layers × 128 neurons, 8000 epochs, batch 256, n_colloc 3000
                  → ~20-30 min on a mid-range GPU
  Override any default via CLI flags.

Phase boundaries scale automatically with --epochs (25% / 50% / 100%).
Best checkpoint saved whenever val MAE improves; reloaded before L-BFGS.
R² reported alongside MAE/RMSE.

Usage
-----
  # Default 30k run:
  python 02_hex_pinn.py --data /path/to/hex_dataset_PINN.csv

  # Override anything:
  python 02_hex_pinn.py --epochs 10000 --batch_size 512 --w_phys 0.05
"""

import argparse
import os
import time
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

# ── reproducibility ───────────────────────────────────────────────────────────
SEED = 42
torch.manual_seed(SEED)
np.random.seed(SEED)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {DEVICE}")

# =============================================================================
# 1.  CLI arguments  —  defaults tuned for 30k dataset
# =============================================================================
parser = argparse.ArgumentParser(description="HEX PINN — 30k dataset")
parser.add_argument("--data",       default="/workspace/11_PINN_Heat Exchanger/hex_dataset_PINN.csv",
                    help="Path to dataset CSV (default: 30k production file)")
parser.add_argument("--epochs",     type=int,   default=2000)
parser.add_argument("--batch_size", type=int,   default=512)
parser.add_argument("--lr",         type=float, default=1e-3)
parser.add_argument("--n_colloc",   type=int,   default=500,
                    help="Collocation points per batch. CPU: 500, GPU: 3000")
parser.add_argument("--w_data",     type=float, default=1.0)
parser.add_argument("--w_phys",     type=float, default=0.1,
                    help="Final physics loss weight (ramped up during phase 2)")
parser.add_argument("--w_bc",       type=float, default=10.0)
parser.add_argument("--hidden_layers", type=int, default=4,
                    help="Hidden layers. CPU-optimised default: 4 (GPU: 6)")
parser.add_argument("--hidden_dim",    type=int, default=64,
                    help="Neurons per layer. CPU-optimised default: 64 (GPU: 128)")
parser.add_argument("--out_dir",    default="/workspace/11_PINN_Heat Exchanger/pinn_outputs_30k",
                    help="Output directory for checkpoints, plots, history")
args = parser.parse_args()

os.makedirs(args.out_dir, exist_ok=True)

# =============================================================================
# 2.  Load & inspect data
# =============================================================================
df = pd.read_csv(args.data)
print(f"\nDataset: {len(df):,} rows × {len(df.columns)} columns  |  {args.data}")

CP      = float(df["cp_hot"].iloc[0])
A_TOTAL = float(df["heat_transfer_area"].iloc[0])
print(f"Cp = {CP} J/kg·K   |   A_total = {A_TOTAL:.4f} m²")

# =============================================================================
# 3.  Feature engineering & normalisation
# =============================================================================
INPUT_COLS  = ["cold_inlet_temp", "hot_inlet_temp",
               "cold_mass_flow",  "hot_mass_flow",
               "global_htc"]        # ξ prepended at runtime

TARGET_COLS = ["hot_outlet_temp", "cold_outlet_temp"]

X_raw       = df[INPUT_COLS].values.astype(np.float32)
T_h_in_raw  = df["hot_inlet_temp"].values.astype(np.float32).reshape(-1, 1)
T_c_in_raw  = df["cold_inlet_temp"].values.astype(np.float32).reshape(-1, 1)
T_h_out_raw = df["hot_outlet_temp"].values.astype(np.float32).reshape(-1, 1)
T_c_out_raw = df["cold_outlet_temp"].values.astype(np.float32).reshape(-1, 1)

# ── Train / val / test  (70 / 15 / 15) ───────────────────────────────────────
idx_all = np.arange(len(df))
idx_trainval, idx_test = train_test_split(idx_all,      test_size=0.15, random_state=SEED)
idx_train,    idx_val  = train_test_split(idx_trainval, test_size=0.176, random_state=SEED)
# 0.176 of 0.85 ≈ 0.15 of total  →  ~70 / 15 / 15 split

print(f"Split  — train: {len(idx_train):,}  val: {len(idx_val):,}  test: {len(idx_test):,}")

def _split(arr, idx): return arr[idx]

X_tr,  X_val,  X_te  = _split(X_raw, idx_train), _split(X_raw, idx_val), _split(X_raw, idx_test)
Thi_tr, Thi_val, Thi_te = _split(T_h_in_raw,  idx_train), _split(T_h_in_raw,  idx_val), _split(T_h_in_raw,  idx_test)
Tci_tr, Tci_val, Tci_te = _split(T_c_in_raw,  idx_train), _split(T_c_in_raw,  idx_val), _split(T_c_in_raw,  idx_test)
Tho_tr, Tho_val, Tho_te = _split(T_h_out_raw, idx_train), _split(T_h_out_raw, idx_val), _split(T_h_out_raw, idx_test)
Tco_tr, Tco_val, Tco_te = _split(T_c_out_raw, idx_train), _split(T_c_out_raw, idx_val), _split(T_c_out_raw, idx_test)

# ── Scalers ───────────────────────────────────────────────────────────────────
x_scaler = StandardScaler()
X_tr_s  = x_scaler.fit_transform(X_tr).astype(np.float32)
X_val_s = x_scaler.transform(X_val).astype(np.float32)
X_te_s  = x_scaler.transform(X_te).astype(np.float32)

# Single shared temperature scaler (all four T columns together)
t_scaler  = StandardScaler()
all_temps = np.concatenate([T_h_in_raw, T_c_in_raw, T_h_out_raw, T_c_out_raw])
t_scaler.fit(all_temps)
T_mean = float(t_scaler.mean_[0])
T_std  = float(t_scaler.scale_[0])
print(f"Temperature scaler : mean = {T_mean:.3f} K  |  std = {T_std:.4f} K")

def scale_T(T_np):   return ((T_np - T_mean) / T_std).astype(np.float32)
def unscale_T(T_sc): return T_sc * T_std + T_mean   # works on tensors and numpy

# ── Scaled BC / target arrays ─────────────────────────────────────────────────
Thi_tr_s,  Thi_val_s,  Thi_te_s  = scale_T(Thi_tr),  scale_T(Thi_val),  scale_T(Thi_te)
Tci_tr_s,  Tci_val_s,  Tci_te_s  = scale_T(Tci_tr),  scale_T(Tci_val),  scale_T(Tci_te)
Tho_tr_s,  Tho_val_s,  Tho_te_s  = scale_T(Tho_tr),  scale_T(Tho_val),  scale_T(Tho_te)
Tco_tr_s,  Tco_val_s,  Tco_te_s  = scale_T(Tco_tr),  scale_T(Tco_val),  scale_T(Tco_te)

# =============================================================================
# 4.  Tensors & DataLoader
# =============================================================================
def to_t(arr): return torch.tensor(arr, dtype=torch.float32, device=DEVICE)

# Raw (unscaled) physics params for ODE residual
#  INPUT_COLS order: [cold_T_in, hot_T_in, cold_mflow, hot_mflow, U]
mc_tr = to_t(X_tr[:, 2:3])   # cold_mass_flow [kg/s]
mh_tr = to_t(X_tr[:, 3:4])   # hot_mass_flow  [kg/s]
U_tr  = to_t(X_tr[:, 4:5])   # global_htc     [W/m²K]

train_ds = TensorDataset(
    to_t(X_tr_s),
    to_t(Thi_tr_s), to_t(Tci_tr_s),
    to_t(Tho_tr_s), to_t(Tco_tr_s),
    mc_tr, mh_tr, U_tr,
)
train_loader = DataLoader(
    train_ds, batch_size=args.batch_size,
    shuffle=True, drop_last=False,
    pin_memory=(DEVICE.type == "cuda"),
    num_workers=0,
)

# Keep validation tensors on device for fast eval
X_val_t   = to_t(X_val_s)
Thi_val_t = to_t(Thi_val_s); Tci_val_t = to_t(Tci_val_s)
Tho_val_t = to_t(Tho_val_s); Tco_val_t = to_t(Tco_val_s)

print(f"Batches per epoch : {len(train_loader):,}")

# =============================================================================
# 5.  PINN Architecture  —  wider & deeper for 30k scale
# =============================================================================
class HexPINN(nn.Module):
    """
    Maps [ξ, x_op_scaled] → [T_h_scaled(ξ), T_c_scaled(ξ)]

    Input  : 1 (ξ) + 5 (operating params) = 6
    Output : 2  (T_h, T_c)

    Activation : Tanh  — smooth, infinitely differentiable, essential for
                         well-behaved autograd derivatives dT/dξ in the ODE.

    30k default  : 6 hidden layers × 128 neurons  ≈ 100k parameters
    300pt version: 4 hidden layers × 64  neurons  ≈ 12k  parameters
    """
    def __init__(self, hidden_layers=6, hidden_dim=128):
        super().__init__()
        seq = [nn.Linear(6, hidden_dim), nn.Tanh()]
        for _ in range(hidden_layers - 1):
            seq += [nn.Linear(hidden_dim, hidden_dim), nn.Tanh()]
        seq.append(nn.Linear(hidden_dim, 2))
        self.net = nn.Sequential(*seq)
        self._init_weights()

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.xavier_normal_(m.weight)
                nn.init.zeros_(m.bias)

    def forward(self, xi, x_op):
        """
        xi   : [N, 1]   normalised position ∈ [0, 1]  (requires_grad=True for physics)
        x_op : [N, 5]   scaled operating parameters
        returns  T_h_scaled [N,1], T_c_scaled [N,1]
        """
        out = self.net(torch.cat([xi, x_op], dim=1))
        return out[:, 0:1], out[:, 1:2]


model = HexPINN(
    hidden_layers=args.hidden_layers,
    hidden_dim=args.hidden_dim,
).to(DEVICE)

total_params = sum(p.numel() for p in model.parameters())
print(f"\nArchitecture : {args.hidden_layers} × {args.hidden_dim}  |  "
      f"Parameters : {total_params:,}")

# =============================================================================
# 6.  Physics residual
# =============================================================================
def physics_residual(model, xi_col, x_op_col, mh_col, mc_col, U_col):
    """
    Evaluates ODE residuals at collocation points.

    Counter-current energy balance ODEs (ξ normalised):
      Hot  :  ṁ_h·Cp · dT_h/dξ  +  U·A · (T_h - T_c) = 0
      Cold :  ṁ_c·Cp · dT_c/dξ  +  U·A · (T_h - T_c) = 0

    Derivatives computed in scaled space then converted to physical [K]
    so residuals carry SI units (K / normalised_length).
    """
    xi_col = xi_col.requires_grad_(True)
    T_h_s, T_c_s = model(xi_col, x_op_col)

    dTh_s = torch.autograd.grad(
        T_h_s, xi_col, grad_outputs=torch.ones_like(T_h_s),
        create_graph=True, retain_graph=True)[0]
    dTc_s = torch.autograd.grad(
        T_c_s, xi_col, grad_outputs=torch.ones_like(T_c_s),
        create_graph=True, retain_graph=True)[0]

    # Convert derivatives to physical units
    dTh_dxi = dTh_s * T_std
    dTc_dxi = dTc_s * T_std

    # Unscale temperatures for driving-force term
    Delta_T = unscale_T(T_h_s) - unscale_T(T_c_s)   # [K]

    # NTU-like coefficient per unit normalised length
    alpha_h = (U_col * A_TOTAL) / (mh_col * CP)
    alpha_c = (U_col * A_TOTAL) / (mc_col * CP)

    res_h = dTh_dxi + alpha_h * Delta_T
    res_c = dTc_dxi + alpha_c * Delta_T

    return res_h, res_c

# =============================================================================
# 7.  Loss function
# =============================================================================
mse = nn.MSELoss()

def compute_loss(model, batch, w_data, w_phys, w_bc, n_colloc):
    (X_b,
     Thi_b, Tci_b,
     Tho_b, Tco_b,
     mc_b, mh_b, U_b) = batch

    N = X_b.shape[0]

    # ── 1. Data loss  (inlet + outlet both streams at ξ=0 and ξ=1) ───────────
    xi_0 = torch.zeros(N, 1, device=DEVICE)
    xi_1 = torch.ones( N, 1, device=DEVICE)

    Th_0, Tc_0 = model(xi_0, X_b)   # hot inlet end  / cold outlet end
    Th_1, Tc_1 = model(xi_1, X_b)   # hot outlet end / cold inlet  end

    loss_data = (mse(Th_0, Thi_b) + mse(Th_1, Tho_b) +   # hot stream
                 mse(Tc_1, Tci_b) + mse(Tc_0, Tco_b))    # cold stream

    # ── 2. BC loss  (inlet pins — higher weight than general data) ────────────
    loss_bc = mse(Th_0, Thi_b) + mse(Tc_1, Tci_b)

    # ── 3. Physics residual at random interior collocation points ─────────────
    xi_col  = torch.rand(n_colloc, 1, device=DEVICE)
    idx_rep = torch.randint(0, N, (n_colloc,), device=DEVICE)
    res_h, res_c = physics_residual(
        model, xi_col,
        X_b[idx_rep], mh_b[idx_rep], mc_b[idx_rep], U_b[idx_rep],
    )
    loss_phys = (res_h**2).mean() + (res_c**2).mean()

    loss_total = w_data * loss_data + w_phys * loss_phys + w_bc * loss_bc
    return loss_total, loss_data.item(), loss_phys.item(), loss_bc.item()

# =============================================================================
# 8.  Training  —  three Adam phases + L-BFGS polish
# =============================================================================
optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
    optimizer, patience=max(50, args.epochs // 20), factor=0.5, min_lr=1e-6,
)

# Phase boundaries — CPU-optimised for 2000 epochs
# Scale linearly with --epochs if you override:
#   Phase 1 = 25% of total  (data warm-start)
#   Phase 2 = 25%-50%       (physics ramp)
#   Phase 3 = 50%-100%      (full joint)
PHASE1_END = max(200,  int(args.epochs * 0.25))
PHASE2_END = max(400,  int(args.epochs * 0.50))
# Phase 3: PHASE2_END → args.epochs

print(f"\n{'='*65}")
print(f" Training PINN  |  {args.epochs} epochs  |  device: {DEVICE}")
print(f"{'='*65}")
print(f" Phase 1 (data only)   : epochs      0 – {PHASE1_END-1:>5}")
print(f" Phase 2 (phys. ramp)  : epochs {PHASE1_END:>5} – {PHASE2_END-1:>5}")
print(f" Phase 3 (full joint)  : epochs {PHASE2_END:>5} – {args.epochs-1:>5}")
print(f"{'='*65}\n")

history = {k: [] for k in
           ["epoch", "loss", "loss_data", "loss_phys", "loss_bc",
            "val_mae_Th", "val_mae_Tc", "val_r2_Th", "val_r2_Tc"]}

def r2_score(pred, true):
    ss_res = np.sum((true - pred)**2)
    ss_tot = np.sum((true - np.mean(true))**2)
    return 1.0 - ss_res / (ss_tot + 1e-12)

LOG_EVERY  = max(10, args.epochs // 40)   # ~40 log lines regardless of epoch count
best_val_mae = float("inf")
best_ckpt    = os.path.join(args.out_dir, "hex_pinn_30k_best.pt")

t0 = time.time()

for epoch in range(args.epochs):

    # ── Loss weight schedule ──────────────────────────────────────────────────
    if epoch < PHASE1_END:
        w_phys_eff = 0.0
        w_bc_eff   = args.w_bc
    elif epoch < PHASE2_END:
        ramp       = (epoch - PHASE1_END) / (PHASE2_END - PHASE1_END)
        w_phys_eff = args.w_phys * ramp
        w_bc_eff   = args.w_bc
    else:
        w_phys_eff = args.w_phys
        w_bc_eff   = args.w_bc

    # ── Mini-batch training step ──────────────────────────────────────────────
    model.train()
    epoch_loss = epoch_ld = epoch_lp = epoch_lb = 0.0

    for batch in train_loader:
        batch = [b.to(DEVICE) for b in batch]
        optimizer.zero_grad()
        loss, ld, lp, lb = compute_loss(
            model, batch,
            w_data=args.w_data,
            w_phys=w_phys_eff,
            w_bc=w_bc_eff,
            n_colloc=args.n_colloc,
        )
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        epoch_loss += loss.item(); epoch_ld += ld
        epoch_lp   += lp;         epoch_lb += lb

    nb = len(train_loader)
    epoch_loss /= nb; epoch_ld /= nb; epoch_lp /= nb; epoch_lb /= nb

    scheduler.step(epoch_loss)

    # ── Validation (every LOG_EVERY epochs) ───────────────────────────────────
    if epoch % LOG_EVERY == 0 or epoch == args.epochs - 1:
        model.eval()
        with torch.no_grad():
            N_v   = X_val_t.shape[0]
            xi_1v = torch.ones( N_v, 1, device=DEVICE)
            xi_0v = torch.zeros(N_v, 1, device=DEVICE)
            Th_s, _  = model(xi_1v, X_val_t)   # hot  outlet at ξ=1
            _,  Tc_s = model(xi_0v, X_val_t)   # cold outlet at ξ=0

        Th_pred = unscale_T(Th_s.cpu().numpy())
        Tc_pred = unscale_T(Tc_s.cpu().numpy())
        Th_true = Tho_val; Tc_true = Tco_val

        mae_h  = float(np.mean(np.abs(Th_pred - Th_true)))
        mae_c  = float(np.mean(np.abs(Tc_pred - Tc_true)))
        r2_h   = float(r2_score(Th_pred, Th_true))
        r2_c   = float(r2_score(Tc_pred, Tc_true))
        lr_now = optimizer.param_groups[0]["lr"]
        elapsed = time.time() - t0

        rate = (epoch + 1) / elapsed if elapsed > 0 else 1
        eta  = (args.epochs - epoch - 1) / rate
        print(f"Ep {epoch:5d} | "
              f"Loss {epoch_loss:.3e} "
              f"(d {epoch_ld:.2e} | p {epoch_lp:.2e} | bc {epoch_lb:.2e}) | "
              f"Val MAE  Th={mae_h:.3f}K  Tc={mae_c:.3f}K | "
              f"R²  Th={r2_h:.4f}  Tc={r2_c:.4f} | "
              f"lr={lr_now:.1e} | {elapsed/60:.1f}min ETA {eta/60:.1f}min")

        for k, v in zip(history.keys(),
                        [epoch, epoch_loss, epoch_ld, epoch_lp, epoch_lb,
                         mae_h, mae_c, r2_h, r2_c]):
            history[k].append(v)

        # Save best checkpoint whenever val MAE improves
        avg_mae = (mae_h + mae_c) / 2
        if avg_mae < best_val_mae:
            best_val_mae = avg_mae
            torch.save(model.state_dict(), best_ckpt)
            print(f"  ✓ Best model saved  (avg MAE = {best_val_mae:.4f} K)")

# =============================================================================
# 9.  L-BFGS polish  —  mini-batch (4096) for 30k-scale RAM safety
# =============================================================================
# Reload the best checkpoint found during Adam training before polishing
print(f"\nLoading best Adam checkpoint: avg MAE = {best_val_mae:.4f} K")
model.load_state_dict(torch.load(best_ckpt, map_location=DEVICE))

print("\n--- Phase 4 : L-BFGS polish (mini-batch) ---")

LBFGS_BATCH = 4096
lbfgs_ds     = DataLoader(train_ds, batch_size=LBFGS_BATCH, shuffle=True)
lbfgs_batch  = [b.to(DEVICE) for b in next(iter(lbfgs_ds))]

lbfgs = torch.optim.LBFGS(
    model.parameters(), lr=0.1,
    max_iter=20, history_size=100,
    line_search_fn="strong_wolfe",
)

lbfgs_steps = 0
def lbfgs_closure():
    global lbfgs_steps
    lbfgs.zero_grad()
    loss, *_ = compute_loss(
        model, lbfgs_batch,
        w_data=args.w_data, w_phys=args.w_phys,
        w_bc=args.w_bc,     n_colloc=args.n_colloc,
    )
    loss.backward()
    lbfgs_steps += 1
    if lbfgs_steps % 25 == 0:
        print(f"  L-BFGS step {lbfgs_steps:4d} | loss {loss.item():.4e}")
    return loss

for _ in range(25):   # 25 outer × max_iter=20 = up to 500 steps
    lbfgs.step(lbfgs_closure)

# =============================================================================
# 10.  Final evaluation  —  validation + held-out test set
# =============================================================================
def evaluate(X_t, Tho_true, Tco_true, label):
    model.eval()
    N = X_t.shape[0]
    with torch.no_grad():
        Th_s, _  = model(torch.ones( N, 1, device=DEVICE), X_t)
        _,  Tc_s = model(torch.zeros(N, 1, device=DEVICE), X_t)
    Th_pred = unscale_T(Th_s.cpu().numpy())
    Tc_pred = unscale_T(Tc_s.cpu().numpy())

    mae_h  = float(np.mean(np.abs(Th_pred - Tho_true)))
    mae_c  = float(np.mean(np.abs(Tc_pred - Tco_true)))
    rmse_h = float(np.sqrt(np.mean((Th_pred - Tho_true)**2)))
    rmse_c = float(np.sqrt(np.mean((Tc_pred - Tco_true)**2)))
    maxe_h = float(np.max(np.abs(Th_pred - Tho_true)))
    maxe_c = float(np.max(np.abs(Tc_pred - Tco_true)))
    r2_h   = float(r2_score(Th_pred, Tho_true))
    r2_c   = float(r2_score(Tc_pred, Tco_true))

    print(f"\n  [{label}]")
    print(f"  Hot  outlet — MAE: {mae_h:.4f} K | RMSE: {rmse_h:.4f} K | "
          f"MaxErr: {maxe_h:.4f} K | R²: {r2_h:.5f}")
    print(f"  Cold outlet — MAE: {mae_c:.4f} K | RMSE: {rmse_c:.4f} K | "
          f"MaxErr: {maxe_c:.4f} K | R²: {r2_c:.5f}")
    return Th_pred, Tc_pred

print("\n--- Final Evaluation ---")
Th_pred_val, Tc_pred_val = evaluate(X_val_t,       Tho_val, Tco_val, "Validation")
Th_pred_te,  Tc_pred_te  = evaluate(to_t(X_te_s),  Tho_te,  Tco_te,  "Test (held-out)")

# =============================================================================
# 11.  Save artefacts
# =============================================================================
ckpt_path = os.path.join(args.out_dir, "hex_pinn_30k.pt")
torch.save({
    "model_state":    model.state_dict(),
    "hidden_layers":  args.hidden_layers,
    "hidden_dim":     args.hidden_dim,
    "x_scaler_mean":  x_scaler.mean_.tolist(),
    "x_scaler_std":   x_scaler.scale_.tolist(),
    "T_mean":         T_mean,
    "T_std":          T_std,
    "A_TOTAL":        A_TOTAL,
    "CP":             CP,
    "input_cols":     INPUT_COLS,
    "best_val_mae_K": best_val_mae,
    "n_train":        len(idx_train),
    "n_val":          len(idx_val),
    "n_test":         len(idx_test),
}, ckpt_path)
print(f"\nModel  saved → {ckpt_path}")

hist_path = os.path.join(args.out_dir, "training_history.csv")
pd.DataFrame(history).to_csv(hist_path, index=False)
print(f"History saved → {hist_path}")

# =============================================================================
# 12.  Plots
# =============================================================================
fig, axes = plt.subplots(1, 3, figsize=(18, 5))

# (a) Loss curves
ax = axes[0]
ep = history["epoch"]
ax.semilogy(ep, history["loss"],       label="Total",   lw=2)
ax.semilogy(ep, history["loss_data"],  label="Data",    lw=1.5, ls="--")
ax.semilogy(ep, history["loss_phys"],  label="Physics", lw=1.5, ls="-.")
ax.semilogy(ep, history["loss_bc"],    label="BC",      lw=1.5, ls=":")
for x_ph, lbl in [(PHASE1_END, "P2"), (PHASE2_END, "P3")]:
    ax.axvline(x_ph, color="grey", ls="--", lw=0.8, alpha=0.7)
    ax.text(x_ph + 20, ax.get_ylim()[0]*1.5, lbl, fontsize=8, color="grey")
ax.set_xlabel("Epoch"); ax.set_ylabel("Loss (log)")
ax.set_title("Training Loss"); ax.legend(fontsize=8); ax.grid(True, alpha=0.3)

# (b) Validation MAE + R²
ax = axes[1]
ax2b = ax.twinx()
ax.plot(ep, history["val_mae_Th"], color="tomato",    lw=2, label="MAE T_h")
ax.plot(ep, history["val_mae_Tc"], color="steelblue", lw=2, label="MAE T_c")
ax2b.plot(ep, history["val_r2_Th"], color="tomato",    lw=1.5, ls="--", alpha=0.6, label="R² T_h")
ax2b.plot(ep, history["val_r2_Tc"], color="steelblue", lw=1.5, ls="--", alpha=0.6, label="R² T_c")
ax.set_xlabel("Epoch"); ax.set_ylabel("MAE [K]"); ax2b.set_ylabel("R²")
ax.set_title("Validation Metrics")
lines1, lab1 = ax.get_legend_handles_labels()
lines2, lab2 = ax2b.get_legend_handles_labels()
ax.legend(lines1 + lines2, lab1 + lab2, fontsize=8)
ax.grid(True, alpha=0.3)

# (c) Parity plot — test set
ax = axes[2]
ax.scatter(Tho_te, Th_pred_te, s=8, alpha=0.3, color="tomato",    label="Hot  outlet")
ax.scatter(Tco_te, Tc_pred_te, s=8, alpha=0.3, color="steelblue", label="Cold outlet")
all_v = np.concatenate([Tho_te.flatten(), Tco_te.flatten()])
lims  = [all_v.min() - 1, all_v.max() + 1]
ax.plot(lims, lims, "k--", lw=1)
ax.set_xlabel("DWSim [K]"); ax.set_ylabel("PINN [K]")
ax.set_title("Parity Plot — Test Set"); ax.legend(fontsize=8); ax.grid(True, alpha=0.3)

plt.tight_layout()
plot_path = os.path.join(args.out_dir, "pinn_training_results.png")
plt.savefig(plot_path, dpi=150, bbox_inches="tight")
print(f"Plot   saved → {plot_path}")

# =============================================================================
# 13.  Temperature profile utility  +  example plot
# =============================================================================
def predict_profile(cold_T_in, hot_T_in, cold_mflow, hot_mflow, U, n_points=200):
    """
    Predict full spatial T_h(ξ) and T_c(ξ) for one operating condition.
    Returns: xi [n_points], T_h_K [n_points], T_c_K [n_points]
    """
    model.eval()
    xi_np   = np.linspace(0, 1, n_points, dtype=np.float32).reshape(-1, 1)
    x_op_s  = x_scaler.transform(
        np.array([[cold_T_in, hot_T_in, cold_mflow, hot_mflow, U]],
                 dtype=np.float32)
    )
    x_op_s  = np.repeat(x_op_s, n_points, axis=0).astype(np.float32)
    with torch.no_grad():
        Th_s, Tc_s = model(to_t(xi_np), to_t(x_op_s))
    return (xi_np.flatten(),
            unscale_T(Th_s.cpu().numpy()).flatten(),
            unscale_T(Tc_s.cpu().numpy()).flatten())

# ── Plot 3 representative profiles from the test set ─────────────────────────
test_df   = df.iloc[idx_test].reset_index(drop=True)
# Pick low / mid / high efficiency cases
eff_vals  = test_df["thermal_efficiency"].values
pick_idx  = [
    int(np.argmin(eff_vals)),
    int(np.argmin(np.abs(eff_vals - np.median(eff_vals)))),
    int(np.argmax(eff_vals)),
]

fig2, axs = plt.subplots(1, 3, figsize=(18, 5), sharey=False)
titles = ["Low efficiency", "Median efficiency", "High efficiency"]

for ax, ti, label in zip(axs, pick_idx, titles):
    r     = test_df.iloc[ti]
    xi_p, Th_p, Tc_p = predict_profile(
        r["cold_inlet_temp"], r["hot_inlet_temp"],
        r["cold_mass_flow"],  r["hot_mass_flow"],
        r["global_htc"],
    )
    ax.plot(xi_p, Th_p, color="tomato",    lw=2.5, label="T_hot(ξ)")
    ax.plot(xi_p, Tc_p, color="steelblue", lw=2.5, label="T_cold(ξ)")
    # DWSim endpoint markers
    ax.scatter([0], [r["hot_inlet_temp"]],   color="tomato",    s=80,
               zorder=5, label=f"T_h in  = {r['hot_inlet_temp']:.1f} K")
    ax.scatter([1], [r["hot_outlet_temp"]],  color="tomato",    s=80, marker="D",
               zorder=5, label=f"T_h out = {r['hot_outlet_temp']:.1f} K (DWSim)")
    ax.scatter([1], [r["cold_inlet_temp"]],  color="steelblue", s=80,
               zorder=5, label=f"T_c in  = {r['cold_inlet_temp']:.1f} K")
    ax.scatter([0], [r["cold_outlet_temp"]], color="steelblue", s=80, marker="D",
               zorder=5, label=f"T_c out = {r['cold_outlet_temp']:.1f} K (DWSim)")
    ax.set_xlabel("ξ = x/L"); ax.set_ylabel("Temperature [K]")
    ax.set_title(f"{label}  (η = {r['thermal_efficiency']:.1f}%)")
    ax.legend(fontsize=7); ax.grid(True, alpha=0.3)

plt.suptitle("PINN Temperature Profiles — Counter-Current HEX  (Test Set)",
             fontsize=12, fontweight="bold", y=1.02)
plt.tight_layout()
profile_path = os.path.join(args.out_dir, "temperature_profiles.png")
plt.savefig(profile_path, dpi=150, bbox_inches="tight")
print(f"Profiles saved → {profile_path}")

print(f"\n{'='*65}")
print(f" Training complete in {(time.time()-t0)/60:.1f} min")
print(f" All outputs saved to : {args.out_dir}/")
print(f"{'='*65}")