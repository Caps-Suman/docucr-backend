# SSH Key Pair for EC2 instances
resource "aws_key_pair" "main" {
  key_name   = "${var.project_name}-key"
  public_key = file("~/Documents/fhrm-pem-key/ssh-key.pub")

  tags = {
    Name = "${var.project_name}-keypair"
  }
}
