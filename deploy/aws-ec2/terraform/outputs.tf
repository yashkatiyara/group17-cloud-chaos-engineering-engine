output "instance_public_ip" {
  description = "Public IP for SSH, dashboard, and target gateway"
  value       = aws_instance.group17.public_ip
}

output "dashboard_url" {
  value = "http://${aws_instance.group17.public_ip}:9000"
}

output "gateway_url" {
  value = "http://${aws_instance.group17.public_ip}:8088"
}
