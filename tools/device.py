# Copyright 2018 Xiaomi, Inc.  All rights reserved.
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

import os
import sys
import socket
import subprocess
import time

import six
import sh
import yaml

import common
from common import *

import sh_commands


class DeviceWrapper:
    allow_scheme = ('ssh', 'adb')

    def __init__(self, device_dict):
        """
        init device with device dict info
        :type device_dict: Device
        :param device_dict: a key-value dict that holds the device information,
                       which attribute has:
                       device_name, target_abis, target_socs, system,
                        address, username
        """
        diff = set(device_dict.keys()) - set(YAMLKeyword.__dict__.keys())
        if len(diff) > 0:
            six.print_('Wrong key detected: ')
            six.print_(diff)
            raise KeyError(str(diff))
        self.__dict__.update(device_dict)
        if self.system == SystemType.android:
            self.data_dir = PHONE_DATA_DIR
            self.interior_dir = self.data_dir + '/interior'
        elif self.system == SystemType.arm_linux:
            try:
                sh.ssh('-q', '{}@{}'.format(self.username, self.address),
                       'exit')
            except sh.ErrorReturnCode as e:
                six.print_('device connect failed, '
                           'please check your authentication')
                raise e
            self.data_dir = DEVICE_DATA_DIR
            self.interior_dir = self.data_dir + '/interior'

    ##################
    #  internal use  #
    ##################

    def exec_command(self, command, *args, **kwargs):
        if self.system == SystemType.android:
            sh.adb('-s', self.address, 'shell', command, *args, **kwargs)
        elif self.system == SystemType.arm_linux:
            sh.ssh('{}@{}'.format(self.username, self.address),
                   command, *args, **kwargs)

    #####################
    #  public interface #
    #####################

    def is_lock(self):
        return sh_commands.is_device_locked(self.address)

    def lock(self):
        return sh_commands.device_lock(self.address)

    def clear_data_dir(self):
        if self.system == SystemType.android:
            sh_commands.clear_phone_data_dir(self.address, PHONE_DATA_DIR)
        elif self.system == SystemType.arm_linux:
            self.exec_command('rm -rf {}'.format(self.data_dir))

    def pull_from_data_dir(self, filename, dst_path):
        if self.system == SystemType.android:
            self.pull(PHONE_DATA_DIR, filename, dst_path)
        elif self.system == SystemType.arm_linux:
            self.pull(DEVICE_DATA_DIR, filename, dst_path)

    def create_internal_storage_dir(self):
        internal_storage_dir = '{}/interior/'.format(self.data_dir)
        if self.system == SystemType.android:
            sh_commands.create_internal_storage_dir(self.address,
                                                    internal_storage_dir)
        elif self.system == SystemType.arm_linux:
            self.exec_command('mkdir -p {}'.format(internal_storage_dir))
        return internal_storage_dir

    def rm(self, file):
        if self.system == SystemType.android:
            sh.adb('-s', self.address, 'shell', 'rm', '-rf', file, _fg=True)
        elif self.system == SystemType.arm_linux:
            self.exec_command('rm -rf {}'.format(file), _fg=True)

    def push(self, src_path, dst_path):
        mace_check(os.path.exists(src_path), "Device",
                   '{} not found'.format(src_path))
        six.print_("Push %s to %s" % (src_path, dst_path))
        if self.system == SystemType.android:
            sh_commands.adb_push(src_path, dst_path, self.address)
        elif self.system == SystemType.arm_linux:
            try:
                sh.scp(src_path, '{}@{}:{}'.format(self.username,
                                                   self.address,
                                                   dst_path))
            except sh.ErrorReturnCode_1 as e:
                six.print_('Push Failed !', e, file=sys.stderr)
                raise e

    def pull(self, src_path, file_name, dst_path='.'):
        if not os.path.exists(dst_path):
            sh.mkdir("-p", dst_path)
        src_file = "%s/%s" % (src_path, file_name)
        dst_file = "%s/%s" % (dst_path, file_name)
        if os.path.exists(dst_file):
            sh.rm('-f', dst_file)
        six.print_("Pull %s to %s" % (src_path, dst_path))
        if self.system == SystemType.android:
            sh_commands.adb_pull(
                src_file, dst_file, self.address)
        elif self.system == SystemType.arm_linux:
            try:
                sh.scp('-r', '%s@%s:%s' % (self.username,
                                           self.address,
                                           src_file),
                       dst_file)
            except sh.ErrorReturnCode_1 as e:
                six.print_("Pull Failed !", file=sys.stderr)
                raise e

    def tuning_run(self,
                   abi,
                   target_dir,
                   target_name,
                   vlog_level,
                   embed_model_data,
                   model_output_dir,
                   input_nodes,
                   output_nodes,
                   input_shapes,
                   output_shapes,
                   mace_model_dir,
                   model_tag,
                   device_type,
                   running_round,
                   restart_round,
                   limit_opencl_kernel_time,
                   tuning,
                   out_of_range_check,
                   model_graph_format,
                   opencl_binary_file,
                   opencl_parameter_file,
                   libmace_dynamic_library_path,
                   omp_num_threads=-1,
                   cpu_affinity_policy=1,
                   gpu_perf_hint=3,
                   gpu_priority_hint=3,
                   input_file_name='model_input',
                   output_file_name='model_out',
                   runtime_failure_ratio=0.0,
                   address_sanitizer=False,
                   link_dynamic=False,
                   quantize_stat=False,
                   ):
        six.print_("* Run '%s' with round=%s, restart_round=%s, tuning=%s, "
                   "out_of_range_check=%s, omp_num_threads=%s, "
                   "cpu_affinity_policy=%s, gpu_perf_hint=%s, "
                   "gpu_priority_hint=%s" %
                   (model_tag, running_round, restart_round, str(tuning),
                    str(out_of_range_check), omp_num_threads,
                    cpu_affinity_policy, gpu_perf_hint, gpu_priority_hint))
        mace_model_path = ""
        if model_graph_format == ModelFormat.file:
            mace_model_path = "%s/%s.pb" % (mace_model_dir, model_tag)
        if self.system == SystemType.host:
            libmace_dynamic_lib_path = \
                os.path.dirname(libmace_dynamic_library_path)
            p = subprocess.Popen(
                [
                    "env",
                    "LD_LIBRARY_PATH=%s" % libmace_dynamic_lib_path,
                    "MACE_CPP_MIN_VLOG_LEVEL=%s" % vlog_level,
                    "MACE_RUNTIME_FAILURE_RATIO=%f" % runtime_failure_ratio,
                    "MACE_LOG_TENSOR_RANGE=%d" % (1 if quantize_stat else 0),
                    "%s/%s" % (target_dir, target_name),
                    "--model_name=%s" % model_tag,
                    "--input_node=%s" % ",".join(input_nodes),
                    "--output_node=%s" % ",".join(output_nodes),
                    "--input_shape=%s" % ":".join(input_shapes),
                    "--output_shape=%s" % ":".join(output_shapes),
                    "--input_file=%s/%s" % (model_output_dir,
                                            input_file_name),
                    "--output_file=%s/%s" % (model_output_dir,
                                             output_file_name),
                    "--model_data_file=%s/%s.data" % (mace_model_dir,
                                                      model_tag),
                    "--device=%s" % device_type,
                    "--round=%s" % running_round,
                    "--restart_round=%s" % restart_round,
                    "--omp_num_threads=%s" % omp_num_threads,
                    "--cpu_affinity_policy=%s" % cpu_affinity_policy,
                    "--gpu_perf_hint=%s" % gpu_perf_hint,
                    "--gpu_priority_hint=%s" % gpu_priority_hint,
                    "--model_file=%s" % mace_model_path,
                ],
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE)
            out, err = p.communicate()
            self.stdout = err + out
            six.print_(self.stdout)
            six.print_("Running finished!\n")
        elif self.system in [SystemType.android, SystemType.arm_linux]:
            self.rm(self.data_dir)
            self.exec_command('mkdir -p {}'.format(self.data_dir))
            internal_storage_dir = self.create_internal_storage_dir()

            for input_name in input_nodes:
                formatted_name = common.formatted_file_name(input_file_name,
                                                            input_name)
                self.push("%s/%s" % (model_output_dir, formatted_name),
                          self.data_dir)
            if self.system == SystemType.android and address_sanitizer:
                self.push(sh_commands.find_asan_rt_library(abi),
                          self.data_dir)

            if not embed_model_data:
                model_data_path = "%s/%s.data" % (mace_model_dir, model_tag)
                mace_check(os.path.exists(model_data_path), "Device",
                           'model data file not found,'
                           ' please convert model first')
                self.push(model_data_path, self.data_dir)

            if device_type == common.DeviceType.GPU:
                if os.path.exists(opencl_binary_file):
                    self.push(opencl_binary_file, self.data_dir)
                if os.path.exists(opencl_parameter_file):
                    self.push(opencl_parameter_file, self.data_dir)

            self.push("third_party/nnlib/libhexagon_controller.so",
                      self.data_dir)

            mace_model_phone_path = ""
            if model_graph_format == ModelFormat.file:
                mace_model_phone_path = "%s/%s.pb" % (self.data_dir,
                                                      model_tag)
                self.push(mace_model_path, mace_model_phone_path)
            if link_dynamic:
                self.push(libmace_dynamic_library_path, self.data_dir)
                if self.system == SystemType.android:
                    sh_commands.push_depended_so_libs(
                        libmace_dynamic_library_path, abi, self.data_dir,
                        self.address)
            self.push("%s/%s" % (target_dir, target_name), self.data_dir)

            stdout_buff = []
            process_output = sh_commands.make_output_processor(stdout_buff)
            cmd = [
                "LD_LIBRARY_PATH=%s" % self.data_dir,
                "MACE_TUNING=%s" % int(tuning),
                "MACE_OUT_OF_RANGE_CHECK=%s" % int(out_of_range_check),
                "MACE_CPP_MIN_VLOG_LEVEL=%s" % vlog_level,
                "MACE_RUN_PARAMETER_PATH=%s/mace_run.config" % self.data_dir,
                "MACE_INTERNAL_STORAGE_PATH=%s" % internal_storage_dir,
                "MACE_LIMIT_OPENCL_KERNEL_TIME=%s" % limit_opencl_kernel_time,
                "MACE_RUNTIME_FAILURE_RATIO=%f" % runtime_failure_ratio,
                "MACE_LOG_TENSOR_RANGE=%d" % (1 if quantize_stat else 0),
            ]
            if self.system == SystemType.android and address_sanitizer:
                cmd.extend([
                    "LD_PRELOAD=%s/%s" %
                    (self.data_dir,
                     sh_commands.asan_rt_library_names(abi))
                ])
            cmd.extend([
                "%s/%s" % (self.data_dir, target_name),
                "--model_name=%s" % model_tag,
                "--input_node=%s" % ",".join(input_nodes),
                "--output_node=%s" % ",".join(output_nodes),
                "--input_shape=%s" % ":".join(input_shapes),
                "--output_shape=%s" % ":".join(output_shapes),
                "--input_file=%s/%s" % (self.data_dir, input_file_name),
                "--output_file=%s/%s" % (self.data_dir, output_file_name),
                "--model_data_file=%s/%s.data" % (self.data_dir, model_tag),
                "--device=%s" % device_type,
                "--round=%s" % running_round,
                "--restart_round=%s" % restart_round,
                "--omp_num_threads=%s" % omp_num_threads,
                "--cpu_affinity_policy=%s" % cpu_affinity_policy,
                "--gpu_perf_hint=%s" % gpu_perf_hint,
                "--gpu_priority_hint=%s" % gpu_priority_hint,
                "--model_file=%s" % mace_model_phone_path,
                "--opencl_binary_file=%s/%s" %
                (self.data_dir, os.path.basename(opencl_binary_file)),
                "--opencl_parameter_file=%s/%s" %
                (self.data_dir, os.path.basename(opencl_parameter_file)),
            ])
            cmd = ' '.join(cmd)
            cmd_file_name = "%s-%s-%s" % ('cmd_file',
                                          model_tag,
                                          str(time.time()))
            cmd_file = "%s/%s" % (self.data_dir, cmd_file_name)
            tmp_cmd_file = "%s/%s" % ('/tmp', cmd_file_name)
            with open(tmp_cmd_file, 'w') as file:
                file.write(cmd)
            self.push(tmp_cmd_file, cmd_file)
            os.remove(tmp_cmd_file)
            self.exec_command('sh {}'.format(cmd_file),
                              _tty_in=True,
                              _out=process_output,
                              _err_to_out=True)
            self.stdout = "".join(stdout_buff)
            if not sh_commands.stdout_success(self.stdout):
                common.MaceLogger.error("Mace Run", "Mace run failed.")

            six.print_("Running finished!\n")
        else:
            six.print_('Unsupported system %s' % self.system, file=sys.stderr)
            raise Exception('Wrong device')

        return self.stdout

    def tuning(self, library_name, model_name, model_config,
               model_graph_format, model_data_format,
               target_abi, mace_lib_type):
        six.print_('* Tuning, it may take some time')
        build_tmp_binary_dir = get_build_binary_dir(library_name, target_abi)
        mace_run_name = MACE_RUN_STATIC_NAME
        link_dynamic = False
        if mace_lib_type == MACELibType.dynamic:
            mace_run_name = MACE_RUN_DYNAMIC_NAME
            link_dynamic = True
        embed_model_data = model_data_format == ModelFormat.code

        # build for specified soc
        # device_wrapper = DeviceWrapper(device)

        model_output_base_dir, model_output_dir, mace_model_dir = \
            get_build_model_dirs(
                library_name, model_name, target_abi, self,
                model_config[YAMLKeyword.model_file_path])

        self.clear_data_dir()

        subgraphs = model_config[YAMLKeyword.subgraphs]
        # generate input data
        sh_commands.gen_random_input(
            model_output_dir,
            subgraphs[0][YAMLKeyword.input_tensors],
            subgraphs[0][YAMLKeyword.input_shapes],
            subgraphs[0][YAMLKeyword.validation_inputs_data],
            input_ranges=subgraphs[0][YAMLKeyword.input_ranges],
            input_data_types=subgraphs[0][YAMLKeyword.input_data_types]
        )

        self.tuning_run(
            abi=target_abi,
            target_dir=build_tmp_binary_dir,
            target_name=mace_run_name,
            vlog_level=0,
            embed_model_data=embed_model_data,
            model_output_dir=model_output_dir,
            input_nodes=subgraphs[0][YAMLKeyword.input_tensors],
            output_nodes=subgraphs[0][YAMLKeyword.output_tensors],
            input_shapes=subgraphs[0][YAMLKeyword.input_shapes],
            output_shapes=subgraphs[0][YAMLKeyword.output_shapes],
            mace_model_dir=mace_model_dir,
            model_tag=model_name,
            device_type=DeviceType.GPU,
            running_round=0,
            restart_round=1,
            limit_opencl_kernel_time=model_config[
                YAMLKeyword.limit_opencl_kernel_time],
            tuning=True,
            out_of_range_check=False,
            model_graph_format=model_graph_format,
            opencl_binary_file='',
            opencl_parameter_file='',
            libmace_dynamic_library_path=LIBMACE_DYNAMIC_PATH,
            link_dynamic=link_dynamic,
        )

        # pull opencl library
        self.pull(self.interior_dir, CL_COMPILED_BINARY_FILE_NAME,
                  '{}/{}'.format(model_output_dir,
                                 BUILD_TMP_OPENCL_BIN_DIR))

        # pull opencl parameter
        self.pull_from_data_dir(CL_TUNED_PARAMETER_FILE_NAME,
                                '{}/{}'.format(model_output_dir,
                                               BUILD_TMP_OPENCL_BIN_DIR))

        six.print_('Tuning done! \n')

    def run_specify_abi(self, flags, configs, target_abi):
        if target_abi not in self.target_abis:
            six.print_('There is no device with soc: %s abi: %s' %
                       (self.target_socs, target_abi))
            return
        library_name = configs[YAMLKeyword.library_name]
        mace_lib_type = flags.mace_lib_type
        embed_model_data = \
            configs[YAMLKeyword.model_data_format] == ModelFormat.code
        build_tmp_binary_dir = get_build_binary_dir(library_name, target_abi)

        # get target name for run
        if flags.example:
            if mace_lib_type == MACELibType.static:
                target_name = EXAMPLE_STATIC_NAME
            else:
                target_name = EXAMPLE_DYNAMIC_NAME
        else:
            if mace_lib_type == MACELibType.static:
                target_name = MACE_RUN_STATIC_NAME
            else:
                target_name = MACE_RUN_DYNAMIC_NAME
        link_dynamic = mace_lib_type == MACELibType.dynamic
        model_output_dirs = []

        for model_name in configs[YAMLKeyword.models]:
            check_model_converted(library_name, model_name,
                                  configs[YAMLKeyword.model_graph_format],
                                  configs[YAMLKeyword.model_data_format],
                                  target_abi)
            if target_abi != ABIType.host:
                self.clear_data_dir()
            MaceLogger.header(
                StringFormatter.block(
                    'Run model {} on {}'.format(model_name, self.device_name)))

            model_config = configs[YAMLKeyword.models][model_name]
            model_runtime = model_config[YAMLKeyword.runtime]
            subgraphs = model_config[YAMLKeyword.subgraphs]

            if not configs[YAMLKeyword.target_socs] \
                    or target_abi == ABIType.host:
                model_output_base_dir, model_output_dir, mace_model_dir = \
                    get_build_model_dirs(
                        library_name, model_name, target_abi, self,
                        model_config[YAMLKeyword.model_file_path])
            else:
                model_output_base_dir, model_output_dir, mace_model_dir = \
                    get_build_model_dirs(
                        library_name, model_name, target_abi, self,
                        model_config[YAMLKeyword.model_file_path])

            # clear temp model output dir
            if os.path.exists(model_output_dir):
                sh.rm('-rf', model_output_dir)
            os.makedirs(model_output_dir)

            is_tuned = False
            model_opencl_output_bin_path = ''
            model_opencl_parameter_path = ''
            if not flags.address_sanitizer \
                    and not flags.example \
                    and target_abi != ABIType.host \
                    and configs[YAMLKeyword.target_socs] \
                    and self.target_socs \
                    and model_runtime in [RuntimeType.gpu,
                                          RuntimeType.cpu_gpu] \
                    and not flags.disable_tuning:
                self.tuning(library_name, model_name, model_config,
                            configs[YAMLKeyword.model_graph_format],
                            configs[YAMLKeyword.model_data_format],
                            target_abi, mace_lib_type)
                model_output_dirs.append(model_output_dir)
                model_opencl_output_bin_path = \
                    '{}/{}/{}'.format(model_output_dir,
                                      BUILD_TMP_OPENCL_BIN_DIR,
                                      CL_COMPILED_BINARY_FILE_NAME)
                model_opencl_parameter_path = \
                    '{}/{}/{}'.format(model_output_dir,
                                      BUILD_TMP_OPENCL_BIN_DIR,
                                      CL_TUNED_PARAMETER_FILE_NAME)
                self.clear_data_dir()
                is_tuned = True
            elif target_abi != ABIType.host and self.target_socs:
                model_opencl_output_bin_path = get_opencl_binary_output_path(
                    library_name, target_abi, self
                )
                model_opencl_parameter_path = get_opencl_parameter_output_path(
                    library_name, target_abi, self
                )
            sh_commands.gen_random_input(
                model_output_dir,
                subgraphs[0][YAMLKeyword.input_tensors],
                subgraphs[0][YAMLKeyword.input_shapes],
                subgraphs[0][YAMLKeyword.validation_inputs_data],
                input_ranges=subgraphs[0][YAMLKeyword.input_ranges],
                input_data_types=subgraphs[0][YAMLKeyword.input_data_types]
            )
            runtime_list = []
            if target_abi == ABIType.host:
                runtime_list.append(RuntimeType.cpu)
            elif model_runtime == RuntimeType.cpu_gpu:
                runtime_list.extend([RuntimeType.cpu, RuntimeType.gpu])
            else:
                runtime_list.append(model_runtime)
            for runtime in runtime_list:
                device_type = parse_device_type(runtime)
                # run for specified soc
                run_output = self.tuning_run(
                    abi=target_abi,
                    target_dir=build_tmp_binary_dir,
                    target_name=target_name,
                    vlog_level=flags.vlog_level,
                    embed_model_data=embed_model_data,
                    model_output_dir=model_output_dir,
                    input_nodes=subgraphs[0][YAMLKeyword.input_tensors],
                    output_nodes=subgraphs[0][YAMLKeyword.output_tensors],
                    input_shapes=subgraphs[0][YAMLKeyword.input_shapes],
                    output_shapes=subgraphs[0][YAMLKeyword.output_shapes],
                    mace_model_dir=mace_model_dir,
                    model_tag=model_name,
                    device_type=device_type,
                    running_round=flags.round,
                    restart_round=flags.restart_round,
                    limit_opencl_kernel_time=model_config[
                        YAMLKeyword.limit_opencl_kernel_time],
                    tuning=False,
                    out_of_range_check=flags.gpu_out_of_range_check,
                    model_graph_format=configs[YAMLKeyword.model_graph_format],
                    omp_num_threads=flags.omp_num_threads,
                    cpu_affinity_policy=flags.cpu_affinity_policy,
                    gpu_perf_hint=flags.gpu_perf_hint,
                    gpu_priority_hint=flags.gpu_priority_hint,
                    runtime_failure_ratio=flags.runtime_failure_ratio,
                    address_sanitizer=flags.address_sanitizer,
                    opencl_binary_file=model_opencl_output_bin_path,
                    opencl_parameter_file=model_opencl_parameter_path,
                    libmace_dynamic_library_path=LIBMACE_DYNAMIC_PATH,
                    link_dynamic=link_dynamic,
                    quantize_stat=flags.quantize_stat,
                )
                if flags.validate:
                    model_file_path, weight_file_path = get_model_files(
                        model_config[YAMLKeyword.model_file_path],
                        model_config[YAMLKeyword.model_sha256_checksum],
                        BUILD_DOWNLOADS_DIR,
                        model_config[YAMLKeyword.weight_file_path],
                        model_config[YAMLKeyword.weight_sha256_checksum]
                    )

                    validate_type = device_type
                    if model_config[YAMLKeyword.quantize] == 1:
                        validate_type = device_type + '_QUANTIZE'
                    sh_commands.validate_model(
                        abi=target_abi,
                        device=self,
                        model_file_path=model_file_path,
                        weight_file_path=weight_file_path,
                        platform=model_config[YAMLKeyword.platform],
                        device_type=device_type,
                        input_nodes=subgraphs[0][YAMLKeyword.input_tensors],
                        output_nodes=subgraphs[0][YAMLKeyword.output_tensors],
                        input_shapes=subgraphs[0][YAMLKeyword.input_shapes],
                        output_shapes=subgraphs[0][YAMLKeyword.output_shapes],
                        model_output_dir=model_output_dir,
                        input_data_types=subgraphs[0][
                            YAMLKeyword.input_data_types],
                        caffe_env=flags.caffe_env,
                        validation_threshold=subgraphs[0][
                            YAMLKeyword.validation_threshold][validate_type],
                        backend=subgraphs[0][YAMLKeyword.backend]
                    )
                if flags.report and flags.round > 0:
                    tuned = is_tuned and device_type == DeviceType.GPU
                    self.report_run_statistics(
                        target_abi=target_abi,
                        model_name=model_name,
                        device_type=device_type,
                        output_dir=flags.report_dir,
                        tuned=tuned
                    )
        if model_output_dirs:
            opencl_output_bin_path = get_opencl_binary_output_path(
                library_name, target_abi, self
            )
            opencl_parameter_bin_path = get_opencl_parameter_output_path(
                library_name, target_abi, self
            )

            # clear opencl output dir
            if os.path.exists(opencl_output_bin_path):
                sh.rm('-rf', opencl_output_bin_path)
            if os.path.exists(opencl_parameter_bin_path):
                sh.rm('-rf', opencl_parameter_bin_path)

            # merge all model's opencl binaries together
            sh_commands.merge_opencl_binaries(
                model_output_dirs, CL_COMPILED_BINARY_FILE_NAME,
                opencl_output_bin_path
            )
            # merge all model's opencl parameter together
            sh_commands.merge_opencl_parameters(
                model_output_dirs, CL_TUNED_PARAMETER_FILE_NAME,
                opencl_parameter_bin_path
            )

    def report_run_statistics(self,
                              target_abi,
                              model_name,
                              device_type,
                              output_dir,
                              tuned):
        metrics = [0] * 3
        for line in self.stdout.split('\n'):
            line = line.strip()
            parts = line.split()
            if len(parts) == 4 and parts[0].startswith('time'):
                metrics[0] = str(float(parts[1]))
                metrics[1] = str(float(parts[2]))
                metrics[2] = str(float(parts[3]))
                break
        report_filename = output_dir + '/report.csv'
        if not os.path.exists(report_filename):
            with open(report_filename, 'w') as f:
                f.write('model_name,device_name,soc,abi,runtime,'
                        'init(ms),warmup(ms),run_avg(ms),tuned\n')

        data_str = '{model_name},{device_name},{soc},{abi},{device_type},' \
                   '{init},{warmup},{run_avg},{tuned}\n'.format(
                    model_name=model_name,
                    device_name=self.device_name,
                    soc=self.target_socs,
                    abi=target_abi,
                    device_type=device_type,
                    init=metrics[0],
                    warmup=metrics[1],
                    run_avg=metrics[2],
                    tuned=tuned)
        with open(report_filename, 'a') as f:
            f.write(data_str)

    def benchmark_model(self,
                        abi,
                        benchmark_binary_dir,
                        benchmark_binary_name,
                        vlog_level,
                        embed_model_data,
                        model_output_dir,
                        mace_model_dir,
                        input_nodes,
                        output_nodes,
                        input_shapes,
                        output_shapes,
                        model_tag,
                        device_type,
                        model_graph_format,
                        opencl_binary_file,
                        opencl_parameter_file,
                        libmace_dynamic_library_path,
                        omp_num_threads=-1,
                        cpu_affinity_policy=1,
                        gpu_perf_hint=3,
                        gpu_priority_hint=3,
                        input_file_name='model_input',
                        link_dynamic=False):
        six.print_('* Benchmark for %s' % model_tag)

        mace_model_path = ''
        if model_graph_format == ModelFormat.file:
            mace_model_path = '%s/%s.pb' % (mace_model_dir, model_tag)
        if abi == ABIType.host:
            libmace_dynamic_lib_dir_path = \
                os.path.dirname(libmace_dynamic_library_path)
            p = subprocess.Popen(
                [
                    'env',
                    'LD_LIBRARY_PATH=%s' % libmace_dynamic_lib_dir_path,
                    'MACE_CPP_MIN_VLOG_LEVEL=%s' % vlog_level,
                    '%s/%s' % (benchmark_binary_dir, benchmark_binary_name),
                    '--model_name=%s' % model_tag,
                    '--input_node=%s' % ','.join(input_nodes),
                    '--output_node=%s' % ','.join(output_nodes),
                    '--input_shape=%s' % ':'.join(input_shapes),
                    '--output_shapes=%s' % ':'.join(output_shapes),
                    '--input_file=%s/%s' % (model_output_dir, input_file_name),
                    '--model_data_file=%s/%s.data' % (mace_model_dir,
                                                      model_tag),
                    '--device=%s' % device_type,
                    '--omp_num_threads=%s' % omp_num_threads,
                    '--cpu_addinity_policy=%s' % cpu_affinity_policy,
                    '--gpu_perf_hint=%s' % gpu_perf_hint,
                    '--gpu_priority_hint=%s' % gpu_priority_hint,
                    '--model_file=%s' % mace_model_path
                ])
            p.wait()
        elif self.system in [SystemType.android, SystemType.arm_linux]:
            self.exec_command('mkdir -p %s' % self.data_dir)
            internal_storage_dir = self.create_internal_storage_dir()
            for input_name in input_nodes:
                formatted_name = formatted_file_name(input_file_name,
                                                     input_name)
                self.push('%s/%s' % (model_output_dir, formatted_name),
                          self.data_dir)
            if not embed_model_data:
                self.push('%s/%s.data' % (mace_model_dir, model_tag),
                          self.data_dir)
            if device_type == common.DeviceType.GPU:
                if os.path.exists(opencl_binary_file):
                    self.push(opencl_binary_file, self.data_dir)
                if os.path.exists(opencl_parameter_file):
                    self.push(opencl_parameter_file, self.data_dir)
            mace_model_device_path = ''
            if model_graph_format == ModelFormat.file:
                mace_model_device_path = '%s/%s.pb' % \
                                         (self.data_dir, model_tag)
                self.push(mace_model_path, mace_model_device_path)
            if link_dynamic:
                self.push(libmace_dynamic_library_path, self.data_dir)
                if self.system == SystemType.android:
                    sh_commands.push_depended_so_libs(
                        libmace_dynamic_library_path, abi, self.data_dir,
                        self.address)
            self.rm('%s/%s' % (self.data_dir, benchmark_binary_name))
            self.push('%s/%s' % (benchmark_binary_dir, benchmark_binary_name),
                      self.data_dir)

            cmd = [
                'LD_LIBRARY_PATH=%s' % self.data_dir,
                'MACE_CPP_MIN_VLOG_LEVEL=%s' % vlog_level,
                'MACE_RUN_PARAMETER_PATH=%s/mace_run.config' % self.data_dir,
                'MACE_INTERNAL_STORAGE_PATH=%s' % internal_storage_dir,
                'MACE_OPENCL_PROFILING=1',
                '%s/%s' % (self.data_dir, benchmark_binary_name),
                '--model_name=%s' % model_tag,
                '--input_node=%s' % ','.join(input_nodes),
                '--output_node=%s' % ','.join(output_nodes),
                '--input_shape=%s' % ':'.join(input_shapes),
                '--output_shape=%s' % ':'.join(output_shapes),
                '--input_file=%s/%s' % (self.data_dir, input_file_name),
                '--model_data_file=%s/%s.data' % (self.data_dir, model_tag),
                '--device=%s' % device_type,
                '--omp_num_threads=%s' % omp_num_threads,
                '--cpu_affinity_policy=%s' % cpu_affinity_policy,
                '--gpu_perf_hint=%s' % gpu_perf_hint,
                '--gpu_priority_hint=%s' % gpu_priority_hint,
                '--model_file=%s' % mace_model_device_path,
                '--opencl_binary_file=%s/%s' %
                (self.data_dir, os.path.basename(opencl_binary_file)),
                '--opencl_parameter_file=%s/%s' %
                (self.data_dir, os.path.basename(opencl_parameter_file))
            ]

            cmd = ' '.join(cmd)
            cmd_file_name = '%s-%s-%s' % \
                            ('cmd_file', model_tag, str(time.time()))

            cmd_file_path = '%s/%s' % (self.data_dir, cmd_file_name)
            tmp_cmd_file = '%s/%s' % ('/tmp', cmd_file_name)
            with open(tmp_cmd_file, 'w') as f:
                f.write(cmd)
            self.push(tmp_cmd_file, cmd_file_path)
            os.remove(tmp_cmd_file)

            if self.system == SystemType.android:
                sh.adb('-s', self.address, 'shell', 'sh', cmd_file_path,
                       _fg=True)
            elif self.system == SystemType.arm_linux:
                sh.ssh('%s@%s' % (self.username, self.address),
                       'sh', cmd_file_path, _fg=True)
            self.rm(cmd_file_path)
            six.print_('Benchmark done! \n')

    def bm_specific_target(self, flags, configs, target_abi):
        library_name = configs[YAMLKeyword.library_name]
        embed_model_data = \
            configs[YAMLKeyword.model_data_format] == ModelFormat.code
        opencl_output_bin_path = ''
        opencl_parameter_path = ''
        link_dynamic = flags.mace_lib_type == MACELibType.dynamic

        if link_dynamic:
            bm_model_binary_name = BM_MODEL_DYNAMIC_NAME
        else:
            bm_model_binary_name = BM_MODEL_STATIC_NAME
        build_tmp_binary_dir = get_build_binary_dir(library_name, target_abi)
        if configs[YAMLKeyword.target_socs] and target_abi != ABIType.host:
            opencl_output_bin_path = get_opencl_binary_output_path(
                library_name, target_abi, self
            )
            opencl_parameter_path = get_opencl_parameter_output_path(
                library_name, target_abi, self
            )

        for model_name in configs[YAMLKeyword.models]:
            check_model_converted(library_name,
                                  model_name,
                                  configs[YAMLKeyword.model_graph_format],
                                  configs[YAMLKeyword.model_data_format],
                                  target_abi)
            MaceLogger.header(
                StringFormatter.block(
                    'Benchmark model %s on %s' % (model_name,
                                                  self.device_name)))
            model_config = configs[YAMLKeyword.models][model_name]
            model_runtime = model_config[YAMLKeyword.runtime]
            subgraphs = model_config[YAMLKeyword.subgraphs]

            model_output_base_dir, model_output_dir, mace_model_dir = \
                get_build_model_dirs(library_name, model_name,
                                     target_abi, self,
                                     model_config[YAMLKeyword.model_file_path])
            if os.path.exists(model_output_dir):
                sh.rm('-rf', model_output_dir)
            os.makedirs(model_output_dir)

            if target_abi != ABIType.host:
                self.clear_data_dir()
            sh_commands.gen_random_input(
                model_output_dir,
                subgraphs[0][YAMLKeyword.input_tensors],
                subgraphs[0][YAMLKeyword.input_shapes],
                subgraphs[0][YAMLKeyword.validation_inputs_data],
                input_ranges=subgraphs[0][YAMLKeyword.input_ranges],
                input_data_types=subgraphs[0][YAMLKeyword.input_data_types]
            )
            runtime_list = []
            if target_abi == ABIType.host:
                runtime_list.append(RuntimeType.cpu)
            elif model_runtime == RuntimeType.cpu_gpu:
                runtime_list.extend([RuntimeType.cpu, RuntimeType.cpu_gpu])
            else:
                runtime_list.append(model_runtime)
            for runtime in runtime_list:
                device_type = parse_device_type(runtime)
                self.benchmark_model(
                    abi=target_abi,
                    benchmark_binary_dir=build_tmp_binary_dir,
                    benchmark_binary_name=bm_model_binary_name,
                    vlog_level=0,
                    embed_model_data=embed_model_data,
                    model_output_dir=model_output_dir,
                    input_nodes=subgraphs[0][YAMLKeyword.input_tensors],
                    output_nodes=subgraphs[0][YAMLKeyword.output_tensors],
                    input_shapes=subgraphs[0][YAMLKeyword.input_shapes],
                    output_shapes=subgraphs[0][YAMLKeyword.output_shapes],
                    mace_model_dir=mace_model_dir,
                    model_tag=model_name,
                    device_type=device_type,
                    model_graph_format=configs[YAMLKeyword.model_graph_format],
                    omp_num_threads=flags.omp_num_threads,
                    cpu_affinity_policy=flags.cpu_affinity_policy,
                    gpu_perf_hint=flags.gpu_perf_hint,
                    gpu_priority_hint=flags.gpu_priority_hint,
                    opencl_binary_file=opencl_output_bin_path,
                    opencl_parameter_file=opencl_parameter_path,
                    libmace_dynamic_library_path=LIBMACE_DYNAMIC_PATH,
                    link_dynamic=link_dynamic
                )

    def run(self,
            abi,
            host_bin_path,
            bin_name,
            args='',
            opencl_profiling=True,
            vlog_level=0,
            out_of_range_check=True,
            address_sanitizer=False,
            simpleperf=False):
        host_bin_full_path = '%s/%s' % (host_bin_path, bin_name)
        device_bin_full_path = '%s/%s' % (self.data_dir, bin_name)
        print(
            '================================================================'
        )
        print('Trying to lock device %s' % self.address)
        with self.lock():
            print('Run on device: %s, %s, %s' %
                  (self.address, self.target_socs, self.device_name))
            self.rm(self.data_dir)
            self.exec_command('mkdir -p %s' % self.data_dir)
            self.push(host_bin_full_path, device_bin_full_path)
            ld_preload = ''
            if address_sanitizer:
                self.push(sh_commands.find_asan_rt_library(abi),
                          self.data_dir)
                ld_preload = 'LD_PRELOAD=%s/%s' % \
                             (self.data_dir,
                              sh_commands.asan_rt_library_names(abi))
            opencl_profiling = 1 if opencl_profiling else 0
            out_of_range_check = 1 if out_of_range_check else 0
            print('Run %s' % device_bin_full_path)
            stdout_buf = []
            process_output = sh_commands.make_output_processor(stdout_buf)

            internal_storage_dir = self.create_internal_storage_dir()

            if simpleperf and self.system == SystemType.android:
                self.push(sh_commands.find_simpleperf_library(abi),
                          self.data_dir)
                simpleperf_cmd = '%s/simpleperf' % self.data_dir
                exec_cmd = [
                    ld_preload,
                    'MACE_OUT_OF_RANGE_CHECK=%s' % out_of_range_check,
                    'MACE_OPENCL_PROFILING=%d' % opencl_profiling,
                    'MACE_INTERNAL_STORAGE_PATH=%s' % internal_storage_dir,
                    'MACE_CPP_MIN_VLOG_LEVEL=%d' % vlog_level,
                    simpleperf_cmd,
                    'stat',
                    '--group',
                    'raw-l1-dcache,raw-l1-dcache-refill',
                    '--group',
                    'raw-l2-dcache,raw-l2-dcache-refill',
                    '--group',
                    'raw-l1-dtlb,raw-l1-dtlb-refill',
                    '--group',
                    'raw-l2-dtlb,raw-l2-dtlb-refill',
                    device_bin_full_path,
                    args,
                ]
            else:
                exec_cmd = [
                    ld_preload,
                    'MACE_OUT_OF_RANGE_CHECK=%d' % out_of_range_check,
                    'MACE_OPENCL_PROFILNG=%d' % opencl_profiling,
                    'MACE_INTERNAL_STORAGE_PATH=%s' % internal_storage_dir,
                    'MACE_CPP_MIN_VLOG_LEVEL=%d' % vlog_level,
                    device_bin_full_path,
                    args
                ]
            exec_cmd = ' '.join(exec_cmd)
            self.exec_command(exec_cmd, _tty_in=True,
                              _out=process_output, _err_to_out=True)
            return ''.join(stdout_buf)


class DeviceManager:
    @classmethod
    def list_adb_device(cls):
        adb_list = sh.adb('devices').stdout.decode('utf-8'). \
                       strip().split('\n')[1:]
        adb_list = [tuple(pair.split('\t')) for pair in adb_list]
        devices = []
        for adb in adb_list:
            prop = sh_commands.adb_getprop_by_serialno(adb[0])
            android = {
                YAMLKeyword.device_name:
                    prop['ro.product.model'].replace(' ', ''),
                YAMLKeyword.target_abis:
                    prop['ro.product.cpu.abilist'].split(','),
                YAMLKeyword.target_socs: prop['ro.board.platform'],
                YAMLKeyword.system: SystemType.android,
                YAMLKeyword.address: adb[0],
                YAMLKeyword.username: '',
            }
            devices.append(android)
        return devices

    @classmethod
    def list_ssh_device(cls, yml):
        with open(yml) as f:
            devices = yaml.load(f.read())
        devices = devices['devices']
        device_list = []
        for name, dev in six.iteritems(devices):
            dev[YAMLKeyword.device_name] = \
                dev[YAMLKeyword.models].replace(' ', '')
            dev[YAMLKeyword.system] = SystemType.arm_linux
            device_list.append(dev)
        return device_list

    @classmethod
    def list_devices(cls, yml):
        devices_list = []
        devices_list.extend(cls.list_adb_device())
        if not yml:
            if os.path.exists('devices.yml'):
                devices_list.extend(cls.list_ssh_device('devices.yml'))
        else:
            if os.path.exists(yml):
                devices_list.extend(cls.list_ssh_device(yml))
            else:
                MaceLogger.error(ModuleName.RUN,
                                 'no ARM linux device config file found')
        host = {
            YAMLKeyword.device_name: SystemType.host,
            YAMLKeyword.target_abis: [ABIType.host],
            YAMLKeyword.target_socs: '',
            YAMLKeyword.system: SystemType.host,
            YAMLKeyword.address: None,

        }
        devices_list.append(host)
        return devices_list


if __name__ == '__main__':
    pass