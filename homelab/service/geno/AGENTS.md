# PXE Provisioning Server

## Project Overview
A temporary containerized service for automated network provisioning of Proxmox nodes in a homelab cluster. This server handles progressive provisioning - automatically assigning the next available node configuration to each new physical machine that connects.

## Network Architecture

### Topology
```
[Home WiFi (192.168.5.0/22)]
         |
    [rainbow-road] (Gateway Node)
    - WiFi: 192.168.5.100/22 (home network)
    - Ethernet (vmbr0): 10.11.0.1/22 (cluster network)
         |
    [Switch] (10.11.0.0/22 network)
         |
    +----+----+----+----+
    |    |    |    |    |
  Node Node Node Node  (Other nodes to be provisioned)
```

### IP Allocation Plan
- **Node Management**: 10.11.0.0/26 (10.11.0.1 - 10.11.0.62)
  - 10.11.0.1: rainbow-road (already configured)
  - 10.11.0.2-10.11.0.6: Nodes to be provisioned
- **Guest VMs/Containers**: 10.11.0.64+ (rest of /22)
- **Provisioning Server**: Will run as container on rainbow-road

### Node Configuration Queue
Nodes will be provisioned in this order as they connect:
1. 10.11.0.2 - peach-beach
2. 10.11.0.3 - moo-moo-meadows  
3. 10.11.0.4 - (name TBD)
4. 10.11.0.5 - (name TBD)

## Provisioning Flow

### Progressive Provisioning Logic
The server maintains state and automatically assigns the next configuration:

```
1. Unknown MAC makes DHCP request
   → Assign next IP from queue (10.11.0.2, then 10.11.0.3, etc.)
   → Create DHCP reservation for that MAC
   → Mark config as "installing"
   → Respond with DHCP offer

2. Node boots, requests answer file via HTTP
   → Serve answer file corresponding to assigned IP
   → Answer file includes webhook back to provisioning server

3. Proxmox installation completes
   → Proxmox hits webhook endpoint
   → Server marks that MAC as "provisioned"

4. Node reboots (or makes subsequent DHCP requests)
   → Server recognizes MAC in "provisioned" list
   → DHCP request is IGNORED/DROPPED
   → Node boots from local disk

5. Next node connects, process repeats from step 1
```

### State Management
The server needs to track:
- **Available configs**: Queue of `[(ip, hostname, answer_file_template), ...]`
- **Installing**: MACs currently being provisioned `{mac: (ip, hostname, timestamp)}`
- **Provisioned**: MACs that have completed setup `{mac: (ip, hostname, completed_timestamp)}`

## Technical Requirements

### Services Needed
1. **DHCP Server** (dnsmasq)
   - Dynamic MAC-based reservation
   - PXE boot options (next-server, boot filename)
   - Ability to ignore specific MACs

2. **TFTP Server** (dnsmasq or standalone)
   - Serve bootloader files
   - Lightweight, only for initial boot stage

3. **HTTP Server** (nginx)
   - Serve Proxmox installer ISO/files
   - Serve dynamically generated answer files
   - Handle webhook endpoint for completion notifications

4. **Provisioning Logic** (Python)
   - State management (JSON file or simple DB)
   - DHCP decision logic (respond or ignore based on MAC)
   - Answer file generation per node
   - Webhook endpoint for completion
   - API/interface for monitoring provisioning status

### Deployment
- **Platform**: LXC container on rainbow-road (Proxmox host)
- **Lifecycle**: Temporary - will be torn down after all nodes are provisioned
- **Storage**: Needs to store Proxmox ISO, bootloader files, answer file templates

## Answer File Configuration

Proxmox answer files support post-installation webhooks:

```toml
[global]
# standard answer file config

[post-installation-webhook]
url = "https://my.endpoint.local/postinst"
cert-fingerprint = "AA:E8:CB:95:B1:..."
```

The provisioning server will:
1. Generate answer files dynamically with node-specific configs
2. Include webhook URL pointing to provisioning server
3. Serve the correct answer file based on requesting IP

## Implementation Considerations

### DHCP Filtering
When a MAC is in the "provisioned" state, dnsmasq can:
- Use `dhcp-host` with `ignore` tag
- Update dnsmasq config and reload (via SIGHUP)
- Or use external script (`dhcp-script` option) for dynamic decisions

### Answer File Serving
Options for dynamic serving:
1. Pre-generate all answer files, serve static files via nginx
2. Use nginx with Lua module for dynamic generation
3. Proxy through Python app for full dynamic control

### Monitoring Interface
Simple web UI or CLI for:
- Viewing current queue state
- Seeing which nodes are installing vs provisioned
- Manual intervention (skip node, reset state, etc.)

## Development Notes

### Project Goals
- Learn enterprise patterns through hands-on implementation
- Take the "scenic route" - prioritize understanding over convenience
- Build extensible infrastructure that can grow
- Practice Infrastructure as Code principles

### Design Philosophy
- Containerized services over host installations
- Clear separation of concerns
- Stateful but simple (avoid over-engineering for 5 nodes)
- Easy to tear down when no longer needed

## Questions to Resolve During Implementation

1. **Answer file storage**: Templates with placeholders, or fully generated per-node?
2. **State persistence**: JSON file, SQLite, or in-memory only?
3. **dnsmasq reload mechanism**: Config file updates + SIGHUP, or scripted filtering?
4. **Webhook security**: Self-signed cert, or skip verification for homelab?
5. **Error handling**: What if webhook never arrives? Manual override needed?
6. **Container base**: Debian, Alpine, Ubuntu? (Consider package availability)

## Success Criteria

The provisioning server is complete when:
- [ ] All 5 nodes successfully provisioned with unique IPs and hostnames
- [ ] DHCP correctly ignores already-provisioned MACs
- [ ] Answer files served with correct per-node configuration
- [ ] Webhook successfully marks nodes as provisioned
- [ ] No manual intervention required between node connections
- [ ] Clear visibility into provisioning state at any time

## Next Steps

1. Set up LXC container on rainbow-road
2. Install base packages (dnsmasq, nginx, Python)
3. Configure dnsmasq for DHCP + TFTP
4. Set up PXE boot files and Proxmox installer
5. Implement provisioning logic and state management
6. Create answer file templates
7. Implement webhook endpoint
8. Test with first node
9. Iterate and provision remaining nodes

---

**Note**: This is a learning project. The implementation should balance "doing it right" with "getting it working" - we're here to learn, not build production infrastructure. Expect iteration and refinement as we discover what works.