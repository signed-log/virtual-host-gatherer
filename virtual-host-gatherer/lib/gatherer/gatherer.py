# SPDX-FileCopyrightText: 2015-2025 SUSE LLC
#
# SPDX-License-Identifier: Apache-2.0

# Copyright (c) 2015--2025 SUSE LLC. All Rights Reserved.
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
Main Gatherer application implementation.
"""

from __future__ import print_function, absolute_import
import sys
import os
import argparse
import json
import logging
import uuid
from logging.handlers import RotatingFileHandler
from os.path import expanduser
from gatherer.modules import WorkerInterface
from collections import OrderedDict


def parse_options():
    """
    Parse command line options.
    """

    home = expanduser("~")
    if home == "/root":
        home = "/var/log"
    log_destination = f"{home}/gatherer.log"
    parser = argparse.ArgumentParser(
        description="Process args for retrieving all the Virtual Machines"
    )
    parser.add_argument(
        "-i",
        "--infile",
        action="store",
        help="json input file or '-' to read from stdin",
    )
    parser.add_argument(
        "-o",
        "--outfile",
        action="store",
        help="to write the output (json) file instead of stdout",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="increase log output verbosity",
    )
    parser.add_argument(
        "-l", "--list-modules", action="store_true", help="list modules with options"
    )
    parser.add_argument(
        "-L",
        "--logfile",
        action="store",
        default=log_destination,
        help=f"path to logfile. Default: {log_destination}",
    )

    return parser.parse_args()


class Gatherer(object):
    """
    Gatherer class.
    """

    def __init__(self, opts=None):
        """
        Constructor.

        :param opts: Command line options (optional).
        :return:
        """

        # Define a minimal opts if not provided.
        if opts is None:
            opts = argparse.Namespace(verbose=0, infile="-")
        self.options = opts

        self.log = logging.getLogger("")

        # Should be skipped when no opts was provided.
        if "logfile" in self.options:
            self._setup_logging()

        self.modules = dict()

    def _setup_logging(self):
        """
        Setup logging for use as a command line tool.

        Note that self.options.logfile must exist to call this method.

        :return: void
        """
        self.log.setLevel(logging.WARNING)

        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        self.log.addHandler(stream_handler)

        file_handler = RotatingFileHandler(
            self.options.logfile, maxBytes=(0x100000 * 5), backupCount=5
        )
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(name)s - %(levelname)s: %(message)s")
        )
        self.log.addHandler(file_handler)

    def list_modules(self):
        """
        List available modules.

        :return: Dictionary of available modules.
        """

        params = dict()
        if not self.modules:
            self._load_modules()
        for modname, inst in list(self.modules.items()):
            moditem = OrderedDict([("module", modname)])
            params[modname] = OrderedDict(
                list(moditem.items()) + list(inst.parameters().items())
            )
        return params

    def _run(self):
        """
        Run gatherer application.

        :return: void
        """

        if not self.modules:
            self._load_modules()

        if self.options.infile == "-":
            mgm_nodes = json.load(sys.stdin)
        else:
            with open(self.options.infile, encoding="utf-8") as input_file:
                mgm_nodes = json.load(input_file)

        output = dict()
        for node in mgm_nodes:
            if self.options.verbose >= 2:
                self.log.debug("Input Node: '%s'", self._remove_passwords(node))

            if "module" not in node:
                self.log.error("Skipping undefined module in the input file.")
                continue
            modname = node["module"]
            if modname not in self.modules:
                self.log.error("Skipping unsupported module '%s'.", modname)
                continue

            worker = self.modules[modname]
            worker.set_node(node)
            output[node.get("id", str(uuid.uuid4()))] = worker.run()

        if self.options.verbose >= 2:
            self.log.debug(
                "Output: '%s'",
                json.dumps(output, sort_keys=True, indent=4, separators=(",", ": ")),
            )

        if self.options.outfile:
            with open(self.options.outfile, "w", encoding="utf-8") as input_file:
                json.dump(
                    output, input_file, sort_keys=True, indent=4, separators=(",", ": ")
                )
        else:
            print(json.dumps(output, sort_keys=True, indent=4, separators=(",", ": ")))

    def main(self):
        """
        Application start.
        :return:
        """

        if self.options.verbose == 1:
            self.log.setLevel(logging.INFO)
        if self.options.verbose >= 2:
            self.log.setLevel(logging.DEBUG)

        if self.options.list_modules:
            installed_modules = self.list_modules()
            if self.options.outfile:
                with open(self.options.outfile, "w", encoding="utf-8") as output_file:
                    json.dump(
                        installed_modules,
                        output_file,
                        sort_keys=False,
                        indent=4,
                        separators=(",", ": "),
                    )
            else:
                print(
                    json.dumps(
                        installed_modules,
                        sort_keys=False,
                        indent=4,
                        separators=(",", ": "),
                    )
                )
            return

        if not self.options.infile:
            self.log.error("Input file was not specified")
            return

        self.log.warning("Scanning began")
        try:
            self._run()
        except Exception as ex:
            self.log.error(ex)
            raise
        self.log.warning("Scanning finished")

    def _load_modules(self):
        """
        Load available modules for the gatherer.
        If module meets the description, but cannot be imported, the ImportError exception is raised.

        :return: void
        """

        mod_path = os.path.dirname(
            __import__(
                "gatherer.modules", globals(), locals(), ["WorkerInterface"], 0
            ).__file__
        )
        self.log.info("module path: %s", mod_path)
        for module_name in [
            item.split(".")[0]
            for item in os.listdir(mod_path)
            if item.endswith(".py") and not item.startswith("__init__")
        ]:
            try:
                self.log.debug('Loading module "%s"', module_name)
                mod = __import__(
                    f"gatherer.modules.{module_name}",
                    globals(),
                    locals(),
                    ["WorkerInterface"],
                    0,
                )
                self.log.debug("Introspection: %s", dir(mod))
                class_ = getattr(mod, module_name)
                if not issubclass(class_, WorkerInterface):
                    self.log.error(
                        'Module "%s" is not a gatherer module, skipping.', module_name
                    )
                    continue
                instance = class_()
                if not instance.valid():
                    self.log.error(
                        'Module "%s" is broken, import aborted.', module_name
                    )
                    continue
                self.modules[module_name] = instance
            except (TypeError, AttributeError, NotImplementedError) as ex:
                self.log.error('Module "%s" is broken, skipping.', module_name)
                self.log.debug("Exception: %s", ex)
            except ImportError:
                self.log.debug('Module "%s" was not loaded.', module_name)
                raise

    def _remove_passwords(self, indict):
        """
        Return a carbon copy of the input data dictionary without
        possible passwords in keys like "password", "passwd", "pass".

        :return dict
        """

        ret = indict.copy()

        for key in ret:
            if key.lower().startswith("pass"):
                ret[key] = "**secret**"
        return ret
