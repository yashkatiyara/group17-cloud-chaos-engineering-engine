variable "aws_region" {
  description = "AWS region for the demonstration host"
  type        = string
  default     = "ap-south-1"
}

variable "vpc_id" {
  description = "Existing VPC ID"
  type        = string
}

variable "subnet_id" {
  description = "Public subnet ID with a route to an Internet Gateway"
  type        = string
}

variable "key_name" {
  description = "Existing EC2 key pair name"
  type        = string
}

variable "admin_cidr" {
  description = "Your public IP/CIDR allowed to SSH (port 22) into the host"
  type        = string
}

variable "dashboard_cidr" {
  description = "CIDR allowed to open the chaos dashboard (port 9000). Safe to leave as 0.0.0.0/0 once CHAOS_API_TOKEN is set, since state-changing endpoints require the token."
  type        = string
  default     = "0.0.0.0/0"
}

variable "demo_cidr" {
  description = "CIDR allowed to call the target gateway (port 8088)"
  type        = string
  default     = "0.0.0.0/0"
}

variable "instance_type" {
  description = "Small host is enough for the teaching demo"
  type        = string
  default     = "t3.small"
}
