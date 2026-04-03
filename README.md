### 🤖 Repository for DWSim Automation

<p align="left">
<a href="https://github.com/virajdesai0309/DWSim-Automation-Repo"><img src="https://img.shields.io/static/v1?logo=github&label=Originator&message=virajdesai0309&color=ff3300" alt="Originator"/></a>
<a href="https://github.com/virajdesai0309/DWSim-Automation-Repo/stargazers"><img src="https://img.shields.io/github/stars/virajdesai0309/DWSim-Automation-Repo.svg?colorB=1a53ff" alt="Stars Badge"/></a>
<a href="https://github.com/virajdesai0309/DWSim-Automation-Repo/network/members"><img src="https://img.shields.io/github/forks/virajdesai0309/DWSim-Automation-Repo" alt="Forks Badge"/></a>
<img src="https://img.shields.io/github/repo-size/virajdesai0309/DWSim-Automation-Repo.svg?colorB=CC66FF&style=flat" alt="Size"/>
<img src="https://img.shields.io/github/languages/top/virajdesai0309/DWSim-Automation-Repo.svg?colorB=996600&style=flat" alt="Language"/>
</p>

This repository contains a collection of exercises related to unit operations automation using **DWSim** – a process simulation software that allows you to create and analyze chemical processes. The exercises demonstrate how to automate unit operations (mixing, separation, distillation, etc.) using DWSim, with code examples, tutorials, and documentation.

> **✨ New:** The entire environment is now **containerised** using Docker. You can run the exercises on any machine (Windows or Linux) without installing DWSim or Python manually – everything is inside a reproducible, isolated container.

---

## 📦 Containerised Setup (Recommended)

Using the provided **Dev Container**, you get:
- DWSim pre‑installed and ready to use.
- Python 3 with all required libraries.
- A consistent, isolated environment that doesn’t interfere with your host system.
- GUI forwarding so you can see and interact with DWSim.

### 🎯 Prerequisites

- **GitHub account** (for cloning the repo).
- **~5 GB free disk space** (for the Docker image and dependencies).
- Basic command‑line familiarity.

---

### 🐳 Step 1: Install Docker

#### For Windows Users
Install **Docker Desktop for Windows** with the **WSL 2 backend**:
1. Enable WSL 2 ([Microsoft guide](https://docs.microsoft.com/en-us/windows/wsl/install)).
2. Download [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/).
3. During installation, check **“Use WSL 2 based engine”**.
4. After installation, go to **Settings > Resources > WSL Integration** and enable integration for your Linux distribution (e.g., Ubuntu).
5. Verify with `docker --version` in a terminal.

#### For Linux Users
Install **Docker Engine** (Ubuntu example):
```bash
# Uninstall old versions
sudo apt remove docker.io docker-doc podman-docker

# Add Docker’s official repository and install
sudo apt update
sudo apt install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io

# Add your user to the docker group (to avoid sudo)
sudo usermod -aG docker $USER
# Log out and back in, then test
docker run hello-world
```

---

### 💻 Step 2: Install Visual Studio Code & the Dev Containers Extension

1. Download and install [Visual Studio Code](https://code.visualstudio.com/).
2. Open VS Code, go to Extensions (`Ctrl+Shift+X`), search for **“Dev Containers”** (by Microsoft) and install it.

---

### 📥 Step 3: Clone the Repository

```bash
git clone https://github.com/virajdesai0309/DWSim-Automation-Repo.git
cd DWSim-Automation-Repo
```

---

### 📂 Step 4: Open the Project in a Container

1. Open the folder in VS Code:
   ```bash
   code .
   ```
2. When VS Code detects the `.devcontainer` configuration, click **“Reopen in Container”** in the bottom‑right prompt.  
   *If the prompt doesn’t appear*: open the Command Palette (`F1` or `Ctrl+Shift+P`) and run **“Dev Containers: Reopen in Container”**.
3. Wait for the first build (a few minutes – the base image and all dependencies are downloaded). You can follow the progress in the VS Code terminal.

Once finished, you are inside the containerised environment. Your local repository folder is mounted at `/workspaces/DWSim-Automation-Repo`.

---

### 🔧 Step 5: Configure Git Identity (Inside the Container)

```bash
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

---

### 🔄 Step 6: Rebuilding the Container (When Needed)

If the `Dockerfile` or `.devcontainer/devcontainer.json` changes, run **“Dev Containers: Rebuild Container”** from the Command Palette (`F1`).

---

### 🧪 Step 7: Using DWSim and Python Scripts

| Task | Command / Action |
|------|------------------|
| **Launch DWSim GUI** | In the VS Code terminal (`Ctrl+~`), type `dwsim`. The DWSim window should appear. |
| **Run a Python automation script** | `python3 /workspaces/DWSim-Automation-Repo/exercises/your_script.py` |
| **Install additional Python packages** | `python3 -m pip install package-name` – for persistence, add the package to `requirements.txt` and rebuild. |
| **Access your files** | All changes inside `/workspaces/DWSim-Automation-Repo` are saved on your host machine. |

---

### ❓ Troubleshooting (Container‑Specific)

**“Cannot open display” error on Linux**  
Run this on your **host** (outside VS Code) before starting the container:
```bash
xhost +local:docker
```

**`docker: command not found` or permission denied**  
- Windows: Make sure Docker Desktop is running (whale icon in system tray).  
- Linux: Ensure you added your user to the `docker` group and logged out/back in.

**Build fails with network error**  
Check your internet connection / corporate proxy and try rebuilding.

**How to update the repo after new commits**  
Inside the container terminal:
```bash
git pull origin main
```

**Where are DWSim project files stored?**  
The container persists files saved at `/home/dwsimuser/DWSIM_Projects` into the `projects/` folder inside your local clone.

---

## 🚀 Getting Started Without Containers (Legacy)

If you prefer to install DWSim natively, you can still follow the exercises without Docker. Download DWSim from the [official website](https://dwsim.inforside.com.br/), then clone this repository and run the scripts directly.

> **Note:** The containerised approach is now the recommended and supported method – it guarantees that all dependencies match the exact versions used in the exercises.

---

## Frequently Asked Questions ❔

### How can I thank you for writing and sharing this tutorial?

You can **⭐ Star** and **ⵖ Fork** this repository. Starring and forking is free, but it tells me and others that this content is helpful.

Go [**`here`**](https://github.com/virajdesai0309/DWSim-Automation-Repo) (if you aren’t already) and click **✰ Star** and **ⵖ Fork** in the top‑right corner.

---

## Author

Hello! My name is **Desai Viraj** and I am the writer of these training modules. If you think you can add, correct, edit, or enhance this tutorial, you are most welcome 🙏

**For contributing to this open‑source repository:**

1. Create a [GitHub account](https://github.com/) and install [Git](https://git-scm.com/).
2. Generate a pull request from the repository (see [Contributors page](https://github.com/virajdesai0309/DWSim-Automation-Repo/graphs/contributors)).
3. Clone the repository locally, commit your changes, and push.

If you have trouble with this tutorial, please [create an issue on GitHub](https://github.com/virajdesai0309/DWSim-Automation-Repo/issues/new). I’ll make it better.

If you like this tutorial, please **give it a ⭐ star**.

---

## Licence 📜

You may use this tutorial freely at your own risk. See [LICENSE](./LICENSE).  
Copyright © 2023 Desai Viraj
```

---

### What changed / what was added

- **Containerisation as the main setup** – the “Getting Started” section now begins with the Docker/Dev Container workflow.
- **Full step‑by‑step guide** – from Docker installation (Windows & Linux) to opening the project in a container and running DWSim.
- **Troubleshooting** – specific errors like `Cannot open display` and permission issues.
- **Legacy note** – still mentions native installation, but clearly recommends the container approach.
- **All original content preserved** – badges, author, FAQ, contribution, and license remain unchanged.

You can copy the markdown above directly into your `README.md` and commit it. If you also want to keep a standalone `CONTAINERIZATION.md` file (e.g., for linking), just extract the container‑specific part from the combined README – but the single file is cleaner for most users.
