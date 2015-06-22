"""
Brainfuck to python compiler. Example:


$ cat mul.bf
read a and b
,>,<

| a | b | c | d |
compute c = a*b using d as temp (pointer starts and ends and a)
[

    sum b to c and copy in d (ends in b)
    >[->+>+<<]

    move d in b (ends in d)
    >>[-<<+>>]

    back on a
    <<<-
]

print c
>>.

$ python bpc.py --comments --memory 5 --optimizations 2 --output a.py mul.bf

$ cat a.py
# -*- coding: UTF-8 -*-
m = [ 0 ] * 5
p = 0

# read a and b
m[p] = int(raw_input("Insert a number: ") or 0)
m[p + 1] = int(raw_input("Insert a number: ") or 0)

# | a | b | c | d |
# compute c = a*b using d as temp (pointer starts and ends and a)
while m[p]:

    # sum b to c and copy in d (ends in b)
    p = (p + 1) % 5
    while m[p]:
        m[p] -= 1
        m[p + 1] += 1
        m[p + 2] += 1

    # move d in b (ends in d)
    p = (p + 2) % 5
    while m[p]:
        m[p] -= 1
        m[p - 2] += 1

    # back on a
    m[p - 3] -= 1
    p = (p - 3) % 5

# print c
print m[p + 2]

$ python a.py
Insert a number: 5
Insert a number: 3
15

$
"""
import click
import re


class CodeBuilder(object):
    """
    Builds the code by incrementally adding statements to it, automatically
    managing code indentation.
    """
    def __init__(self, indent_size=4, indent_char=' '):
        self.code = list()
        self.indent = 0
        self.indent_size = indent_size
        self.indent_char = indent_char

    def start_block(self):
        self.indent += self.indent_size

    def end_block(self):
        self.indent -= self.indent_size
        assert self.indent >= 0

    def append(self, statements):
        self.code += [self.indent_char * self.indent + s for s in statements.split('\n')]

    def stream_code(self):
        comment, first_line = False, True
        for row in self.code:
            if re.match(r'^\s*#', row):
                if not comment and not first_line:
                    yield ''
                comment = True
            else:
                comment = False
            yield row
            first_line = False

    def get_code(self):
        return '\n'.join(c for c in self.stream_code())


class Tokenizer(object):
    """
    Splits the code into tokens (either instructions or comments). Generates an
    event for each token and when the process has finished.
    """
    instruction_set = set(['+', '-', '<', '>', '.', ',', ']', '['])

    def __init__(self):
        self.handlers = {
            'finish': list(),
            'instruction': list(),
            'comment': list(),
        }

    def _invoke_handlers(self, handler_type, *args, **kwargs):
        for handler in self.handlers[handler_type]:
            handler(handler_type, *args, **kwargs)

    def register_handler(self, message_type, handler):
        assert message_type in self.handlers.keys()
        self.handlers[message_type].append(handler)

    def tokenize(self, code):
        i, code_length = 0, len(code)
        while i < code_length:
            if code[i] in self.instruction_set:
                self._invoke_handlers('instruction', code[i], i)
                i += 1
            else:
                start = i
                while i < code_length and not code[i] in self.instruction_set:
                    i += 1
                self._invoke_handlers('comment', code[start:i], start, i)

        self._invoke_handlers('finish')


class Compiler0(object):
    """
    Simple and direct translation of brainfuck instructions into their python equivalent.
    """
    def __init__(self, tokenizer, builder, memory_size, comments, dump_memory):
        self.memory_size = memory_size
        self.dump_memory = dump_memory
        self.comments = comments
        self.builder = builder
        self.tokenizer = tokenizer

        self.tokenizer.register_handler('instruction', self.on_instruction)
        self.tokenizer.register_handler('finish', self.on_finish)

        if self.comments:
            self.tokenizer.register_handler('comment', self.on_comment)

        self.write_incipit()

    def write_incipit(self):
        self.builder.append('# -*- coding: UTF-8 -*-')
        self.builder.append('m = [ 0 ] * %d' % self.memory_size)
        self.builder.append('p = 0')

    def on_instruction(self, _type, instruction, *args, **kwargs):
        if instruction == '+' or instruction == '-':
            self.builder.append('m[p] %s= 1' % instruction)
        elif instruction == '<':
            self.builder.append('p = (p - 1) %% %d' % self.memory_size)
        elif instruction == '>':
            self.builder.append('p = (p + 1) %% %d' % self.memory_size)
        elif instruction == ',':
            self.builder.append('m[p] = int(raw_input("Insert a number: ") or 0)')
        elif instruction == '.':
            self.builder.append('print m[p]')
        elif instruction == '[':
            self.builder.append('while m[p]:')
            self.builder.start_block()
        elif instruction == ']':
            self.builder.end_block()

    def on_comment(self, _type, comment, *args, **kwargs):
        for comment in (c.strip() for c in comment.split('\n')):
            if comment:
                self.builder.append('# ' + comment)

    def on_finish(self, _type, *args, **kwargs):
        assert self.builder.indent == 0, 'Some loops are not closed'
        if self.dump_memory:
            self._write_dump_memory()

    def _write_dump_memory(self):
        if self.comments:
            self.builder.append('# dump the memory')
        self.builder.append(
            "print '\\n~~~ Program Terminated ~~~'\n"
            "print 'Pointer:', p\n"
            "print 'Memory:'\n"
            "m += [ 0 ] * ({dump_step} - {memory_size} % {dump_step})\n"
            "dump = ('{{:4d}}' * {dump_step}).format\n"
            "for i in range(0, {memory_size}, {dump_step}):\n"
            "    print '{{:7d}} | {{}}'.format(i, dump(*m[i:i + {dump_step}]))\n"
            "".format(memory_size=self.memory_size, dump_step=16))


class Compiler1(Compiler0):
    """
    Compiles the code and aggregates similar operations to a single macro instruction.
    For example, '+++' becomes 'm[p]+=3', '<<<<' becomes 'p-=4' and so on.
    """
    def __init__(self, *args, **kwargs):
        super(Compiler1, self).__init__(*args, **kwargs)

        self.operation, self.times = None, 0
        self.accumulated = set(['+', '-', '<', '>'])

    def _flush(self):
        if self.operation == '+' or self.operation == '-':
            self.builder.append('m[p] %s= %d' % (self.operation, self.times))
        elif self.operation == '<':
            self.builder.append('p = (p - %d) %% %d' % (self.times, self.memory_size))
        elif self.operation == '>':
            self.builder.append('p = (p + %d) %% %d' % (self.times, self.memory_size))

    def on_finish(self, *args, **kwargs):
        self._flush()
        super(Compiler1, self).on_finish(*args, **kwargs)

    def on_instruction(self, _type, instruction, *args, **kwargs):
        if instruction in self.accumulated:
            if instruction == self.operation:
                self.times += 1
            else:
                self._flush()
                self.times, self.operation = 1, instruction
        else:
            self._flush()
            self.times, self.operation = 0, None
            super(Compiler1, self).on_instruction(_type, instruction, *args, **kwargs)


class Compiler2(Compiler0):
    """
    Caches the pointer movements and uses relative offsets to index memory whenever possible.
    Also aggregates identical brainfuck instructions into a single python statement.
    """
    def __init__(self, *args, **kwargs):
        super(Compiler2, self).__init__(*args, **kwargs)

        self.operation = None
        self.times = self.pointer_move = self.pointer_position = 0
        self.accumulated = set(['+', '-', '<', '>'])

    def _get_relative_pointer_string(self):
        if self.pointer_move:
            return 'p %s %d' % (['-', '+'][self.pointer_move > 0], abs(self.pointer_move))
        else:
            return 'p'

    def _flush(self):
        if self.operation == '+' or self.operation == '-':
            self.builder.append('m[%s] %s= %d' % (self._get_relative_pointer_string(),
                                                  self.operation, self.times))
        elif self.operation == '<':
            self.pointer_move -= self.times
        elif self.operation == '>':
            self.pointer_move += self.times

    def _commit_pointer(self):
        if self.pointer_move:
            self.builder.append('p = (%s) %% %d' % (self._get_relative_pointer_string(),
                                                    self.memory_size))
            self.pointer_move = 0

    def on_instruction(self, _type, instruction, *args, **kwargs):
        if instruction in self.accumulated and instruction == self.operation:
            self.times += 1
            return

        self._flush()
        self.times, self.operation = 1, instruction

        if instruction == ',':
            self.builder.append('m[%s] = int(raw_input("Insert a number: ") or 0)' %
                                self._get_relative_pointer_string())
        elif instruction == '.':
            self.builder.append('print m[%s]' % self._get_relative_pointer_string())
        elif instruction == '[':
            self._commit_pointer()
            self.builder.append('while m[%s]:' % self._get_relative_pointer_string())
            self.builder.start_block()
        elif instruction == ']':
            self._commit_pointer()
            self.builder.end_block()


def compile(code, memory, comments, dump, indent, tab_indent, optimizations):
    """
    Compiles the given brainfuck code into python.
    """
    assert memory > 0, 'Memory must be larger than 0'
    assert indent > 0, 'Indentation width must be larger than 0'
    assert optimizations in set([0, 1, 2]), 'Optimization level must be 0, 1 or 2'

    builder = CodeBuilder(indent_size=indent, indent_char='\t' if tab_indent else ' ')
    tokenizer = Tokenizer()

    compiler_cls = (Compiler0 if optimizations == 0 else
                    Compiler1 if optimizations == 1 else Compiler2)
    compiler = compiler_cls(tokenizer, builder, memory, comments, dump)

    tokenizer.tokenize(code)

    return builder.get_code()


@click.command()
@click.argument('input', type=click.File('r'))
@click.option('--output', '-o', type=click.File('w'), default='a.py',
              help='Compiled python file name or \'-\' for stdout.')
@click.option('--memory', '-m', default=1024,
              help='The size of the memory used by the program.')
@click.option('--comments/--no-comments', '-c', default=False,
              help='Include comments in generated file.')
@click.option('--dump/--no-dump', '-d', default=False,
              help='Dump the memory and the pointer at the end of the program')
@click.option('--indent', '-i', default=4,
              help='Number of characters used to indent the code.')
@click.option('--tab-indent/--space-indent', '-t', default=False,
              help='Indent with tabs or spaces.')
@click.option('--optimizations', '-O', default=2,
              help='Optimization level (0, 1, 2)')
# aggiungere dimensione celle
# aggiugere stile di memoria (extend-on-overflow, wrap-around, throw-exception)
def main_cli(input, output, *args, **kwargs):
    code = input.read()
    compiled = compile(code, *args, **kwargs)
    output.write(compiled)


if __name__ == '__main__':
    main_cli()
