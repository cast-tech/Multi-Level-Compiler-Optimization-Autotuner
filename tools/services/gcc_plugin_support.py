import os

from tools.services.enhanced_builder import EnhancedBuilder
from tools.services.enhanced_builder import EnhancedBuilderError
from tools.services.gcc_optimization_flags import (
    BINARY_OPTIMIZATION_KEYS_ALL as SHARED_BINARY_OPTIMIZATION_KEYS_ALL,
)
from tools.services.gcc_optimization_flags import (
    BINARY_OPTIMIZATION_KEYS_REDUCED as SHARED_BINARY_OPTIMIZATION_KEYS_REDUCED,
)
from tools.services.gcc_optimization_flags import FLAG_SET_CHOICES as SHARED_FLAG_SET_CHOICES
from tools.services.gcc_optimization_flags import get_optimization_keys as get_shared_optimization_keys


class PluginConfigGenerator:
    OPTIMIZATION_LEVEL_KEY = "level"

    BINARY_OPTIMIZATION_KEYS_ALL = SHARED_BINARY_OPTIMIZATION_KEYS_ALL
    BINARY_OPTIMIZATION_KEYS_REDUCED = SHARED_BINARY_OPTIMIZATION_KEYS_REDUCED
    BINARY_OPTIMIZATION_KEYS = BINARY_OPTIMIZATION_KEYS_REDUCED
    FLAG_SET_CHOICES = SHARED_FLAG_SET_CHOICES

    @staticmethod
    def get_optimization_keys(flag_set):
        return get_shared_optimization_keys(flag_set)

    def __init__(self, output_dir, flag_set="reduced"):
        self.plugin_config_filepath = os.path.join(output_dir, 'plugin_optimizations.cfg')
        self.flag_set = flag_set
        self.BINARY_OPTIMIZATION_KEYS = self.get_optimization_keys(flag_set)

    @staticmethod
    def check_if_entry_keys_are_valid(optimization_entry, valid_keys):
        if any(k not in valid_keys for k in optimization_entry):
            raise EnhancedBuilderError("Invalid key in optimization config entry")

    def check_if_optimizations_are_supported(self, optimization_entry):
        if any((k not in self.BINARY_OPTIMIZATION_KEYS and k != self.OPTIMIZATION_LEVEL_KEY)
               for k in optimization_entry["optimizations"]):
            raise EnhancedBuilderError("Optimization not supported in config entry")

    def get_optimization_entry_content(self, optimization_entry):
        if 'type' not in optimization_entry:
            raise EnhancedBuilderError("No optimization entry type specified")
        if optimization_entry['type'] == 'function':
            valid_keys = ["type", "filename", "optimizations", "line_number", "function_name"]
        elif optimization_entry['type'] == 'module':
            valid_keys = ["type", "filename", "optimizations"]
        else:
            raise EnhancedBuilderError("Unknown optimization entry type")
        self.check_if_entry_keys_are_valid(optimization_entry, valid_keys)
        self.check_if_optimizations_are_supported(optimization_entry)
        content = ""
        for key in optimization_entry:
            if key == "optimizations":
                continue
            content += f"{key}={optimization_entry[key]}\n"
        for key in optimization_entry["optimizations"]:
            content += f"opt-{key}={optimization_entry['optimizations'][key]}\n"
        return content

    def get_optimization_config_content(self, optimization_config):
        config_contents = []
        for optimization_entry in optimization_config:
            config_contents.append(self.get_optimization_entry_content(optimization_entry))
        return "---\n".join(config_contents)

    def generate_optimization_config_file(self, optimization_config):
        with open(self.plugin_config_filepath, "w") as f:
            f.write(self.get_optimization_config_content(optimization_config))


class PluginEnhancedBuilder(EnhancedBuilder):
    def __init__(self, builder, gcc_plugin_path, output_dir, flag_set="reduced"):
        self.builder = builder
        self.gcc_plugin_path = gcc_plugin_path
        self.config_generator = PluginConfigGenerator(output_dir, flag_set)

    def build_with_optimizations(self, optimization_config, flags):
        self.config_generator.generate_optimization_config_file(optimization_config)
        return self.builder.build(flags + [f"-fplugin={self.gcc_plugin_path}",
                                           f"-fplugin-arg-cxx_optimizer-config={self.config_generator.plugin_config_filepath}"])
