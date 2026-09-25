import argparse
import opentuner
import json
import os

from tools.implementations.builders.spec_builder import SPECBuilder
from tools.implementations.runners.spec_runner import SPECRunner
from tools.services.iterative_tuner import run_phase_3, three_phase_iterative_tune
from tools.services.gcc_wrapper_support import WrapperEnhancedBuilder
from tools.services.combined_builder import CombinedEnhancedBuilder, CombinedConfigGenerator
from tools.services.simple_tuner import SimpleEnhancedBuilder


def create_argparser():
    argparser = argparse.ArgumentParser(parents=opentuner.argparsers())
    argparser.add_argument('--spec-root', help='Path to the spec root directory', required=True)
    argparser.add_argument('--spec-benchmark', help='Name of the spec benchmark', required=True)
    argparser.add_argument('--spec-config', help='Path to the spec config file', required=True)
    argparser.add_argument('--spec-threads-count', help='Number of threads for the spec run', type=int, default=1)
    argparser.add_argument('--spec-iterations-count', help='Number of iterations for the spec run', type=int, default=1)
    argparser.add_argument('--spec-size', help='Size of the spec run', choices=['test', 'train', 'refspeed'], default='test')
    argparser.add_argument('--spec-core-count', help='Number of cores for the spec build', type=int, default=1)
    argparser.add_argument('--compiler-bin', help='Path to the compiler bin directory', required=True)
    argparser.add_argument('--gcc-wrapper-bin', help='Path to the gcc wrapper bin directory', required=True)
    argparser.add_argument('--gcc-plugin', help='Path to the gcc plugin .so file', required=True)
    argparser.add_argument('--module-entries', help='Path to the module-level optimization entries JSON', required=True)
    argparser.add_argument('--function-entries', help='Path to the function-level optimization entries JSON', required=True)
    argparser.add_argument('--output-dir', help='Path to the output directory', required=True)
    argparser.add_argument('--flag-set', choices=CombinedConfigGenerator.FLAG_SET_CHOICES,
                           default='reduced',
                           help='GCC optimization flag set used by all three phases')
    argparser.add_argument('--timeout', help='Program running timeout in seconds', type=int, default=10)
    argparser.add_argument('--runner-cores', help='Cores to set to taskset during runner run', type=str, default='')
    argparser.add_argument('--phase3-only', '--phase2-only', dest='phase3_only', action='store_true',
                           help='Skip global and module-level tuning and run only function-level tuning, '
                                'loading fixed global flags from <output-dir>/global_base_flags.json and '
                                'fixed module config from <output-dir>/optimization_config.json')
    return argparser


def load_json(json_path):
    with open(json_path, 'r') as f:
        return json.load(f)


def main():
    args = create_argparser().parse_args()

    combined_base_builder = SPECBuilder(args.spec_root, args.spec_benchmark, args.spec_config, args.output_dir, args.spec_core_count, args.gcc_wrapper_bin)
    combined_builder = CombinedEnhancedBuilder(
        combined_base_builder, args.gcc_wrapper_bin, args.compiler_bin,
        args.gcc_plugin, args.output_dir, args.flag_set)
    combined_runner = SPECRunner(args.spec_threads_count, args.spec_iterations_count, args.spec_size, args.timeout, args.runner_cores)

    function_entries = load_json(args.function_entries)

    if args.phase3_only:
        os.makedirs(args.output_dir, exist_ok=True)
        final_config_path = os.path.join(args.output_dir, "optimization_config.json")
        global_flags_path = os.path.join(args.output_dir, "global_base_flags.json")
        fixed_module_config = load_json(final_config_path)
        base_flags = load_json(global_flags_path) if os.path.isfile(global_flags_path) else ["-O3"]
        run_phase_3(args, combined_runner, combined_builder, function_entries,
                    args.output_dir, base_flags, fixed_module_config, phase3_only=True)
    else:
        global_base_builder = SPECBuilder(args.spec_root, args.spec_benchmark, args.spec_config, args.output_dir, args.spec_core_count, args.compiler_bin)
        # Tune the same flag set the later (wrapper/plugin) stages use.
        global_builder = SimpleEnhancedBuilder(global_base_builder, flag_set=args.flag_set)
        global_runner = SPECRunner(args.spec_threads_count, args.spec_iterations_count, args.spec_size, args.timeout, args.runner_cores)

        module_base_builder = SPECBuilder(args.spec_root, args.spec_benchmark, args.spec_config, args.output_dir, args.spec_core_count, args.gcc_wrapper_bin)
        module_builder = WrapperEnhancedBuilder(
            module_base_builder, args.gcc_wrapper_bin, args.compiler_bin,
            args.output_dir, args.flag_set)
        module_runner = SPECRunner(args.spec_threads_count, args.spec_iterations_count, args.spec_size, args.timeout, args.runner_cores)

        module_entries = load_json(args.module_entries)
        three_phase_iterative_tune(args, global_runner, module_runner, combined_runner,
                                   global_builder, module_builder, combined_builder,
                                   module_entries, function_entries, args.output_dir)


if __name__ == "__main__":
    main()
