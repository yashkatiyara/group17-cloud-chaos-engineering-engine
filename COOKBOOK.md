# Cookbook — Group 17 Chaos Engineering Engine

Practical, copy-pasteable recipes for running, operating, and extending this project.
For an explanation of *what* the project is, see [README.md](README.md) and
[docs/PRESENTATION_GUIDE.md](docs/PRESENTATION_GUIDE.md).

---

## Recipe 1 — Run it locally (Docker)

```bash
cp .env.example .env     # defaults are fine for a local demo
./start.sh
```

Wait for `🚀 SYSTEM READY!`. Then open:

- Dashboard: http://localhost:9000
- Target app: http://localhost:8088

Stop everything:
```bash
./stop.sh
```

---

## Recipe 2 — Run the automated resilience test

Proves the full fault → breach → rollback cycle without touching the UI, and exits
non-zero if it doesn't happen:

```bash
python3 test_demo.py
```

Point it at a different host (e.g. the cloud deployment) with env vars:
```bash
GATEWAY_URL=http://<ip>:8088 CHAOS_URL=http://<ip>:9000 CHAOS_API_TOKEN=<token> python3 test_demo.py
```

---

## Recipe 3 — Run a chaos experiment from the command line (no UI)

```bash
# List available experiments
curl -s http://localhost:9000/api/experiments | python3 -m json.tool

# Launch one (add -H "X-Chaos-Token: <token>" if CHAOS_API_TOKEN is set)
curl -s -X POST http://localhost:9000/api/experiments/01_instance_termination/run

# Watch live status
watch -n1 'curl -s http://localhost:9000/api/status | python3 -m json.tool'

# Emergency rollback at any time
curl -s -X POST http://localhost:9000/api/rollback
```

---

## Recipe 4 — Add a new chaos experiment

Drop a new YAML file into `experiments/` — it's picked up automatically on the next
container restart (the scheduler loads every `.yaml`/`.yml` file in that directory).

```yaml
id: "05_my_new_experiment"
name: "My New Experiment"
description: "What this simulates, in one sentence."
target: "gateway"              # inventory-service | order-service | gateway
fault:
  type: "network_latency"      # container_kill | network_latency | network_partition | cpu_stress
  duration_seconds: 20
  delay_ms: 500                # only used by network_latency

steady_state_hypothesis:
  max_error_rate_percent: 15.0
  max_p95_latency_ms: 800.0
  probe_interval_seconds: 1.0
  consecutive_breaches_allowed: 2

rollback:
  auto_rollback: true
  recovery_action: "auto"
```

Restart just the control plane to pick it up: `docker compose restart chaos-engine`.

---

## Recipe 5 — Deploy to a real AWS EC2 host

Requires: AWS credentials configured (`aws configure`), Terraform installed, an
existing VPC/public subnet, and an EC2 key pair (create one with
`aws ec2 create-key-pair --key-name my-key --query 'KeyMaterial' --output text > my-key.pem && chmod 400 my-key.pem`
if you don't have one).

```bash
cd deploy/aws-ec2/terraform
terraform init
terraform apply \
  -var='vpc_id=vpc-xxxxxxxx' \
  -var='subnet_id=subnet-xxxxxxxx' \
  -var='key_name=my-key' \
  -var='admin_cidr=YOUR.PUBLIC.IP/32' \
  -var='demo_cidr=YOUR.PUBLIC.IP/32'
```

Then upload and start the stack on the new host:
```bash
IP=$(terraform output -raw instance_public_ip)
cd ../../..   # back to project root
rsync -az -e "ssh -i deploy/aws-ec2/terraform/my-key.pem -o StrictHostKeyChecking=accept-new" \
  --exclude='__pycache__' --exclude='.git' --exclude='deploy' \
  ./ ubuntu@$IP:/opt/group17/chaos_engineering_project/

ssh -i deploy/aws-ec2/terraform/my-key.pem ubuntu@$IP \
  "cd /opt/group17/chaos_engineering_project && \
   printf 'DEPLOYMENT_MODE=aws-ec2-docker\nCLOUD_PROVIDER=aws\nCHAOS_API_TOKEN=%s\n' \$(openssl rand -hex 32) > .env && \
   chmod +x start.sh && ./start.sh"
```

---

## Recipe 6 — Your IP changed and the cloud dashboard stopped responding

The security group only allows `admin_cidr`/`demo_cidr`. If your ISP gave you a new
IP (common after a router restart or a new day), re-apply with the new one:

```bash
curl -s https://ifconfig.me   # your current public IP
cd deploy/aws-ec2/terraform
terraform apply -auto-approve \
  -var='vpc_id=vpc-xxxxxxxx' \
  -var='subnet_id=subnet-xxxxxxxx' \
  -var='key_name=my-key' \
  -var='admin_cidr=<new-ip>/32' \
  -var='demo_cidr=<new-ip>/32'
```

---

## Recipe 7 — Tear down the AWS host (stop billing)

```bash
cd deploy/aws-ec2/terraform
terraform destroy \
  -var='vpc_id=vpc-xxxxxxxx' \
  -var='subnet_id=subnet-xxxxxxxx' \
  -var='key_name=my-key' \
  -var='admin_cidr=YOUR.PUBLIC.IP/32' \
  -var='demo_cidr=YOUR.PUBLIC.IP/32'
```

Always do this after a presentation/demo — the instance bills continuously while running.

---

## Recipe 8 — Regenerate the presentation screenshots, video, and PDF

The dashboard's sticky navbar can duplicate itself in full-page screenshots unless
disabled first — see `docs/PRESENTATION_GUIDE.md` for why. Quick recipe using a
headless browser (e.g. Playwright):

1. Reset to a clean baseline: `curl -s -X POST http://localhost:9000/api/rollback`
2. Navigate to the dashboard, then run in-page:
   `document.querySelector('.navbar').style.position = 'static'`
3. Take full-page screenshots at each stage: baseline → click "Run Experiment" →
   degraded → tripped/recovered → expand the glossary.
4. Build the PDF from `docs/PRESENTATION_GUIDE.md`:
   ```bash
   cd docs
   pandoc PRESENTATION_GUIDE.md -o PRESENTATION_GUIDE.pdf \
     --pdf-engine=weasyprint --css=pdf_style.css \
     -V margin-top=15mm -V margin-bottom=15mm -V margin-left=18mm -V margin-right=18mm
   ```

---

## Recipe 9 — Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `start.sh` fails at step 1 | Docker daemon not running | Start Docker Desktop/systemd Docker |
| Containers unhealthy forever | Port 8088/9000/5001/5002 already in use | `docker compose down` then retry, or free the port |
| Chaos Engine can't inject faults (`docker_runtime_connected: false`) | `/var/run/docker.sock` not mounted or no `NET_ADMIN` cap | Confirm `docker-compose.yml` volumes/`cap_add` weren't edited out |
| Experiment never trips the breaker | SLO thresholds too loose for your hardware's baseline latency | Lower `max_p95_latency_ms` / `max_error_rate_percent` in the experiment YAML |
| `401 Unauthorized` calling `/api/experiments/.../run` | `CHAOS_API_TOKEN` is set but you didn't send `X-Chaos-Token` | Paste the token into the dashboard's token box, or add the header to `curl` |
| Cloud dashboard unreachable but `docker compose ps` shows healthy | Your public IP changed since the security group was created | See Recipe 6 |

---

## Recipe 10 — Clean shutdown / full reset

```bash
./stop.sh                 # stop and remove local containers
docker compose down -v    # also remove the chaos-net network
cd deploy/aws-ec2/terraform && terraform destroy ...   # if you deployed to AWS (Recipe 7)
```
