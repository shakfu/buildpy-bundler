"""
BuiltinModule
FrozenModule
SourceModule
ExtensionModule
Package
"""

import modulegraph2



class DepReport:
    DEFAULT_EXCLUDES = [
        'test',
        'distutils',
        'setuptools',
        'unittest',
        'email',
    ]
    def __init__(self, module, excludes=None):
        self.module = module
        self.mg = modulegraph2.ModuleGraph()
        if not excludes:
            excludes = self.DEFAULT_EXCLUDES
        self.mg.add_excludes(excludes)
        self.mg.add_module(module)
        self.nodes = []
        self.packages = set()
        self.builtins = set()
        self.extensions = set()
        self.frozen = set()
        self.source = set()
        self.bytcode = set()    
        self.namespace_packages = set()
        self.setup()

    @property
    def n_modules(self):
        return len(self.modules)

    @property
    def n_packages(self):
        return len(self.packages)

    @property
    def n_builtins(self):
        return len(self.builtins)

    @property
    def n_extensions(self):
        return len(self.extensions)

    @property
    def n_frozen(self):
        return len(self.frozen)

    @property
    def n_source(self):
        return len(self.source)

    @property
    def n_bytecode(self):
        return len(self.bytecode)

    @property
    def n_namespace_packages(self):
        return len(self.namespace_packages)

    def __repr__(self):
        return f"<DepReport '{self.module}' s:{self.n_source} p:{self.n_packages} b:{self.n_builtins} e:{self.n_extensions} f:{self.n_frozen}>"

    def outgoing_for(self, name):
        return list(i[1].name for i in self.mg.outgoing(self.mg.find_node(name)))

    def incoming_for(self, name):
        return list(i[1].name for i in self.mg.incoming(self.mg.find_node(name)))

    @property
    def outgoing(self):
        return list(i[1].name for i in self.mg.outgoing(self.nodes[0]))

    @property
    def incoming(self):
        return list(i[1].name for i in self.mg.incoming(self.nodes[0]))

    def setup(self):
        norm = lambda name: name.split('.')[0] if '.' in name else name

        self.nodes = list(self.mg.iter_graph()) 

        for i in self.nodes:
            if isinstance(i, modulegraph2.Package):
                self.packages.add(norm(i.name))

            elif isinstance(i, modulegraph2.ExtensionModule):
                self.extensions.add(norm(i.name))

            elif isinstance(i, modulegraph2.BuiltinModule):
                self.builtins.add(norm(i.name))

            elif isinstance(i, modulegraph2.FrozenModule):
                self.frozen.add(norm(i.name))

            elif isinstance(i, modulegraph2.SourceModule):
                self.source.add(i.name)

            elif isinstance(i, modulegraph2.BytecodeModule):
                self.bytecode.add(i.name)

            elif isinstance(i, modulegraph2.NamespacePackage):
                self.namespace_packages.add(i.name)

            else:
                continue

if __name__ == '__main__':
    profile = False
    if not profile:
        d = DepReport('sqlite3')
    else:
        import cProfile
        import pstats

        cProfile.run("DepReport('sqlite3')", "depreport_stats")
        p = pstats.Stats("depreport_stats")
        p.sort_stats("cumulative").print_stats()

