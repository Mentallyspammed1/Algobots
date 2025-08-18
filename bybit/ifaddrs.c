#include <ifaddrs.h>
#include <stdlib.h>

void freeifaddrs(struct ifaddrs *ifa) {
    // This is a stub. A real implementation would free the memory.
}

int getifaddrs(struct ifaddrs **ifap) {
    *ifap = NULL;
    return 0;
}
