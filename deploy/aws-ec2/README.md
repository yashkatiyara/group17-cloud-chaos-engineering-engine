# AWS EC2 cloud deployment

This is the cloud version of the same project. AWS provides the EC2 VM, VPC networking and security group; Docker Compose runs the gateway, order service, inventory service and chaos control plane on that VM. The control plane intentionally injects faults into Docker workloads rather than terminating the EC2 host, so the demonstration is repeatable and does not risk the cloud account.

## 1. Provision a restricted EC2 host

Requirements: AWS credentials, Terraform 1.5+, an existing VPC/public subnet, and an EC2 key pair.

```bash
cd deploy/aws-ec2/terraform
terraform init
terraform apply \
  -var='vpc_id=vpc-xxxxxxxx' \
  -var='subnet_id=subnet-xxxxxxxx' \
  -var='key_name=your-keypair' \
  -var='admin_cidr=YOUR.PUBLIC.IP/32' \
  -var='demo_cidr=YOUR.PUBLIC.IP/32'
```

Only SSH and the dashboard are allowed from `admin_cidr`; port 8088 is allowed from `demo_cidr`. Ports 5001 and 5002 remain private to the Docker network.

## 2. Upload and start the project

From the directory containing this project:

```bash
PUBLIC_IP=$(terraform -chdir=deploy/aws-ec2/terraform output -raw instance_public_ip)
scp -i /path/to/key.pem -r chaos_engineering_project ubuntu@$PUBLIC_IP:/opt/group17/
ssh -i /path/to/key.pem ubuntu@$PUBLIC_IP
cd /opt/group17/chaos_engineering_project
printf 'DEPLOYMENT_MODE=aws-ec2-docker\nCLOUD_PROVIDER=aws\nCHAOS_API_TOKEN=%s\n' "$(openssl rand -hex 32)" > .env
./start.sh
```

The first image build can take a few minutes. Verify the host before presenting:

```bash
curl http://localhost:9000/healthz
curl http://localhost:8088/health
python3 test_demo.py
```

Open the Terraform `dashboard_url` from the allowed admin IP. Paste the token from `.env` into the dashboard token box before running an experiment.

## 3. Explain the cloud-to-Docker mapping

| Cloud primitive | Project implementation |
| --- | --- |
| EC2 compute | Docker host for the demo fleet |
| VPC + security group | External access control; internal service network is `chaos-net` |
| Container runtime | Target microservices and control plane |
| Docker API socket | Control-plane actuator for stop/start and exec-based faults |
| `tc netem` / `iptables` | Repeatable network fault injection inside target containers |
| HTTP health probes | SLO telemetry and circuit-breaker input |

## Safety notes

This project is intentionally a teaching/demo control plane. Do not expose port 9000 to `0.0.0.0/0`, do not mount the Docker socket into an internet-facing service, and use a temporary AWS account or sandbox. Destroy the host after the presentation:

```bash
terraform destroy \
  -var='vpc_id=vpc-xxxxxxxx' \
  -var='subnet_id=subnet-xxxxxxxx' \
  -var='key_name=your-keypair' \
  -var='admin_cidr=YOUR.PUBLIC.IP/32' \
  -var='demo_cidr=YOUR.PUBLIC.IP/32'
```
