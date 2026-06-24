# Test user -- will be deleted
resource "proxmox_virtual_environment_user" "test" {
  comment = "Test user managed by the Terraform -- do not use"
  user_id = "fakeuser@pve"
  enabled = false
}