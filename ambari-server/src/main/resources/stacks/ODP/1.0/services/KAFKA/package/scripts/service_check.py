#!/usr/bin/env python3
"""
Licensed to the Apache Software Foundation (ASF) under one
or more contributor license agreements.  See the NOTICE file
distributed with this work for additional information
regarding copyright ownership.  The ASF licenses this file
to you under the Apache License, Version 2.0 (the
"License"); you may not use this file except in compliance
with the License.  You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

"""
from resource_management.libraries.script.script import Script
from resource_management.libraries.functions.validate import call_and_match_output
from resource_management.core import shell
from resource_management.libraries.functions.format import format
from resource_management.core.logger import Logger
from resource_management.core.exceptions import Fail
from resource_management.core import sudo
from resource_management.core.source import InlineTemplate
from resource_management.core.resources.system import File
from resource_management.core.resources.system import Execute


class ServiceCheck(Script):
  def service_check(self, env):
    import params
    env.set_params(params)

    # TODO, Kafka Service check should be more robust , It should get all the broker_hosts
    # Produce some messages and check if consumer reads same no.of messages.

    kafka_config = self.read_kafka_config()
    topic = "ambari_kafka_service_check"
    create_topic_cmd_created_output = "Created topic ambari_kafka_service_check."
    create_topic_cmd_exists_output = "Topic \'ambari_kafka_service_check\' already exists."
    if params.kerberos_security_enabled:
      kafka_kinit_cmd = format("{kinit_path_local} -kt {kafka_keytab_path} {kafka_jaas_principal};")
      Execute(kafka_kinit_cmd, user=params.kafka_user)

    cmdfile = format("{tmp_dir}/kafka_cmd_configs")
    File(format(cmdfile),
      owner=params.kafka_user,
      content=InlineTemplate("security.protocol="+ params.kafka_security_protocol)
     )
    source_cmd = format(". {conf_dir}/kafka-env.sh")
    topic_exists_cmd = format(source_cmd + " ; " + "{kafka_home}/bin/kafka-topics.sh --bootstrap-server {params.kafka_bootstrap_servers} --topic {topic} --list --command-config {cmdfile}")
    topic_exists_cmd_code, topic_exists_cmd_out = shell.call(topic_exists_cmd, logoutput=True, quiet=False, user=params.kafka_user)

    if topic_exists_cmd_code > 0:
      raise Fail("Error encountered when attempting to list topics: {0}".format(topic_exists_cmd_out))

    if not params.kafka_delete_topic_enable:
      Logger.info('Kafka delete.topic.enable is not enabled. Skipping topic creation: %s' % topic)
      return

      # run create topic command only if the topic doesn't exists
    if topic not in topic_exists_cmd_out:
      create_topic_cmd = format("{kafka_home}/bin/kafka-topics.sh --bootstrap-server {params.kafka_bootstrap_servers} --create --topic {topic} --partitions 1 --replication-factor 1 --command-config {cmdfile}")
      command = source_cmd + " ; " + create_topic_cmd
      Logger.info("Running kafka create topic command: %s" % command)
      call_and_match_output(command, format("({create_topic_cmd_created_output})|({create_topic_cmd_exists_output})"), "Failed to check that topic exists", user=params.kafka_user)

    under_rep_cmd = format(source_cmd + " ; " + "{kafka_home}/bin/kafka-topics.sh --describe --bootstrap-server {params.kafka_bootstrap_servers} --under-replicated-partitions --command-config {cmdfile}")
    under_rep_cmd_code, under_rep_cmd_out = shell.call(under_rep_cmd, logoutput=True, quiet=False, user=params.kafka_user)

    if under_rep_cmd_code > 0:
      raise Fail("Error encountered when attempting find under replicated partitions: {0}".format(under_rep_cmd_out))
    elif len(under_rep_cmd_out) > 0 and "Topic" in under_rep_cmd_out:
      Logger.warning("Under replicated partitions found: {0}".format(under_rep_cmd_out))

  def read_kafka_config(self):
    import params

    kafka_config = {}
    content = sudo.read_file(params.conf_dir + "/server.properties").decode()
    for line in content.splitlines():
      if line.startswith("#") or not line.strip():
        continue

      key, value = line.split("=")
      kafka_config[key] = value.replace("\n", "")

    return kafka_config

if __name__ == "__main__":
    ServiceCheck().execute()