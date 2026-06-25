# Test user -- will be deleted
resource "proxmox_virtual_environment_user" "test" {
  comment = "Test user managed by terraform -- do not use"
  user_id = "fakeuser2@pve"
  enabled = false
}