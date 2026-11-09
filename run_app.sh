#!/bin/bash
# Start the arc-tech Streamlit app in tmux on port 8501 (reachable over Tailscale: http://spark-516b:8501)
# Usage: ./run_app.sh            live (Ollama + GitLab)
#        ARC_OFFLINE=1 ./run_app.sh   cache replay only (demo fallback)
cd "$(dirname "$0")"
tmux kill-session -t arctech 2>/dev/null
tmux new-session -d -s arctech "ARC_OFFLINE=${ARC_OFFLINE:-0} .venv/bin/streamlit run app/Problem.py --server.port 8501 --server.address 0.0.0.0 --server.headless true --browser.gatherUsageStats false 2>&1 | tee logs/app.log"
sleep 3; tail -5 logs/app.log
