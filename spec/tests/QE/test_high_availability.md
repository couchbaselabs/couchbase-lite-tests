# SGW High Availability Tests

## test_sgw_high_availability_with_load_balancer

Test that clients reaching Sync Gateway through a load balancer keep working when one
of the three nodes goes offline during concurrent SDK writes, and that the node catches
up once it is brought back.  The load balancer round robins over the three nodes, so
every step here is served by whichever node comes next.

1. Configure database on all SGW nodes
2. Create user 'vipul' with access to channels ['*']
3. Create user client via load balancer
4. Add initial 100 documents via load balancer
5. Verify all documents are visible via load balancer
6. Start concurrent SDK writes in background
7. Take SG2 offline
8. Verify load balancer still works with SG2 offline
9. Wait for SDK writes to complete and verify via load balancer
10. Bring SG2 back online, and wait for the database to be online on every node
11. Write final documents through the load balancer, round robin over all 3 nodes
12. For each node, force the load balancer to it with header X-Backend=sg-<index>, and
    verify that node serves every document
