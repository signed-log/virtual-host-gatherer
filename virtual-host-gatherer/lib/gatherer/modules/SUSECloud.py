# pylint: disable=invalid-name
# Copyright (c) 2015 SUSE LLC, Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
SUSE Cloud Worker module implementation.
"""

from __future__ import print_function, absolute_import
import json
import logging
from gatherer.modules import WorkerInterface
from collections import OrderedDict

try:
    from novaclient.v1_1 import client

    IS_VALID = True
except ImportError as ex:
    IS_VALID = False


class SUSECloud(WorkerInterface):
    """
    Worker class for the SUSE Cloud.
    """

    DEFAULT_PARAMETERS = OrderedDict(
        [
            ("hostname", ""),
            ("port", 5000),
            ("username", ""),
            ("password", ""),
            ("protocol", "https"),
            ("tenant", "openstack"),
        ]
    )

    # pylint: disable-next=super-init-not-called
    def __init__(self):
        """
        Constructor.

        :return:
        """

        self.log = logging.getLogger(__name__)
        self.host = self.port = self.user = self.password = self.tenant = None

    # pylint: disable=R0801
    def set_node(self, node):
        """
        Set node information

        :param node: Dictionary of the node description.
        :return: void
        """

        try:
            self._validate_parameters(node)
        except AttributeError as error:
            self.log.error(error)
            raise error

        self.host = node["hostname"]
        self.port = node.get("port", 5000)
        self.user = node["username"]
        self.password = node["password"]
        self.tenant = node["tenant"]

    def parameters(self):
        """
        Return default parameters

        :return: default parameter dictionary
        """
        return self.DEFAULT_PARAMETERS

    def run(self):
        """
        Start worker.
        :return: Dictionary of the hosts in the worker scope.
        """

        output = dict()
        url = f"http://{self.host}:{self.port}/v2.0/"
        self.log.info(
            "Connect to %s for tenant %s as user %s", url, self.tenant, self.user
        )
        cloud_client = client.Client(
            self.user, self.password, self.tenant, url, service_type="compute"
        )
        for hyp in cloud_client.hypervisors.list():
            htype = "qemu"
            if hyp.hypervisor_type.lower() in [
                "fully_virtualized",
                "para_virtualized",
                "qemu",
                "vmware",
                "hyperv",
                "virtage",
                "virtualbox",
            ]:
                htype = hyp.hypervisor_type.lower()
            cpu_info = json.loads(hyp.cpu_info)
            output[hyp.hypervisor_hostname] = {
                "name": hyp.hypervisor_hostname,
                "hostIdentifier": hyp.hypervisor_hostname,
                "type": htype,
                "os": hyp.hypervisor_type,
                "osVersion": hyp.hypervisor_version,
                "totalCpuSockets": cpu_info.get("topology", {}).get("sockets"),
                "totalCpuCores": cpu_info.get("topology", {}).get("cores"),
                "totalCpuThreads": cpu_info.get("topology", {}).get("threads"),
                "cpuMhz": 0,
                "cpuVendor": cpu_info.get("vendor"),
                "cpuDescription": cpu_info.get("model"),
                "cpuArch": cpu_info.get("arch"),
                "ramMb": hyp.memory_mb,
                "vms": {},
            }
            for result in cloud_client.hypervisors.search(
                hyp.hypervisor_hostname, True
            ):
                if hasattr(result, "servers"):
                    for virtual_machine in result.servers:
                        output[hyp.hypervisor_hostname]["vms"][
                            virtual_machine["name"]
                        ] = virtual_machine["uuid"]

        return output

    def valid(self):
        """
        Check plugin class validity.

        :return: True, if the current module has novaclient installed.
        """
        return IS_VALID
