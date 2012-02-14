#!/usr/bin/env python

# Copyright (c) 2012, Robert Escriva
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#     * Redistributions of source code must retain the above copyright notice,
#       this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright notice,
#       this list of conditions and the following disclaimer in the documentation
#       and/or other materials provided with the distribution.
#     * Neither the name of deftsilo nor the names of its contributors may be
#       used to endorse or promote products derived from this software without
#       specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
# ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.


from __future__ import absolute_import
from __future__ import with_statement
from __future__ import print_function

import collections
import getopt
import hashlib
import os
import shlex
import subprocess
import tarfile

import argparse


Copy = collections.namedtuple('Copy', 'lineno src dst')
Link = collections.namedtuple('Link', 'lineno src dst')
Mkdir = collections.namedtuple('Mkdir', 'lineno dst')


def get_sha1s_for(relativeto, path):
    path = os.path.normpath(path)
    cmdline = ['git', 'whatchanged', '--follow', '--no-abbrev', '--oneline', path]
    pipe = subprocess.Popen(cmdline, shell=False, stdout=subprocess.PIPE, cwd=relativeto)
    stdout, stderr = pipe.communicate()
    ret = []
    for line in stdout.split('\n'):
        if not line.startswith(':'):
            continue
        sha1 = line.split(' ')[3]
        shapipe = subprocess.Popen(["git", "cat-file", "blob", sha1],
                    shell=False, stdout=subprocess.PIPE)
        stdout, stderr = shapipe.communicate()
        ret.append(hashlib.sha1(stdout).hexdigest())
    return ret


def pathscheme_base(path, level):
    components = []
    for i in range(level):
        head, tail = os.path.split(path)
        components.append(tail)
        path = head
    out = '.' + os.path.basename(path)
    return os.path.join(out, *reversed(components))


def parse_generic(lineno, args, cmd, cmd_type):
    try:
        opts, args = getopt.getopt(args, 'i:p:')
    except getopt.GetoptError as e:
        errstr = '{0} on line {1}'.format(str(e), lineno)
        raise RuntimeError(errstr)
    src = None
    dst = None
    if len(args) == 1:
        p = None
        scheme = 'basename'
        schemes = {'verbatim': lambda x, p: x
                  ,'basename': pathscheme_base
                  }
        for k, v in opts:
            if k == '-p':
                try:
                    p = int(v)
                except ValueError:
                    errstr = 'invalid value "{0}" to "-p" argument on line {1}'
                    raise RuntimeError(errstr.format(v, lineno))
            elif k == '-i':
                if v not in schemes:
                    errstr = 'invalid inference type "{0}" in "-i" argument on line {1}'
                    raise RuntimeError(errstr.format(v, lineno))
                scheme = v
            else:
                errstr = 'invalid argument {1} to "{0}" command on line {2}'
                raise RuntimeError(errstr.format(cmd, k, lineno))
        if scheme != 'basename' and p is not None:
            errstr = '"-p" argument is incompatible with scheme "{0}" on line {1}'
            raise RuntimeError(errstr.format(scheme, lineno))
        src = args[0]
        dst = schemes[scheme](src, p or 0)
    elif len(args) == 2:
        if len(opts):
            errstr = '"{0}" command with two paths does not accept "{1}" on line {2}'
            badopts = ' '.join([' '.join(o) for o in opts])
            raise RuntimeError(errstr.format(cmd, badopts, lineno))
        src, dst = args
    elif len(args) < 1:
        errstr = '"{0}" command takes at least 1 argument ({1} given) on line {2}'
        raise RuntimeError(errstr.format(cmd, len(args), lineno))
    elif len(args) > 2:
        errstr = '"{0}" command takes at most 2 arguments ({1} given) on line {2}'
        raise RuntimeError(errstr.format(cmd, len(args), lineno))
    return cmd_type(lineno, src, dst)


def parse_copy(lineno, args):
    return parse_generic(lineno, args, 'copy', Copy)


def parse_link(lineno, args):
    return parse_generic(lineno, args, 'link', Link)


def parse_mkdir(lineno, args):
    if len(args) != 1:
        errstr = '"mkdir" command takes exactly 1 argument ({0} given) on line {1}'
        raise RuntimeError(errstr.format(len(args), lineno))
    return Mkdir(lineno, args[0])


def parse_line(lineno, args):
    assert len(args) > 0
    parse_funcs = {'copy': parse_copy
                  ,'link': parse_link
                  ,'mkdir': parse_mkdir
                  }
    if args[0] in parse_funcs:
        return parse_funcs[args[0]](lineno, args[1:])
    else:
        errstr = 'Unknown command "{0}" on line {1}'
        raise RuntimeError(errstr.format(args[0], lineno))


def parse(inputfile):
    source = open(inputfile).read()
    actions = []
    command = ''
    count = 1
    for i, line in enumerate(source.split('\n')):
        if line.endswith('\\'):
            command += line[:-1] + ' '
        elif line:
            command += line
            args = shlex.split(command, posix=True)
            newargs = []
            for arg in args:
                if arg.startswith('#'):
                    break
                newargs.append(arg)
            args = newargs
            if len(args) != 0:
                action = parse_line(count, args)
                actions.append(action)
            command = ''
            count = i + 2
    return actions


def shell_escape(path):
    return path


def sha1_cases(relativeto, src):
    sha1s = get_sha1s_for(relativeto, src)
    return ''.join([s + ') ;;\n' + ' ' * 8 for s in sha1s])


def safe_dst(action):
    return '"${DESTDIR}"/' + shell_escape(action.dst)


def safe_src_dst(action):
    src = '"${RELATIVETO}"/' + shell_escape(action.src)
    dst = safe_dst(action)
    return src, dst


def generate_copy_check(relativeto, copy):
    src, dst = safe_src_dst(copy)
    sha1hashes = sha1_cases(relativeto, copy.src)
    ret = '''# Generated from line number {lineno} in {filename}
if test -f {dst}; then
    case `dshash {dst}` in
        {sha1hashes}*) ${{SHTOOL}} echo cannot copy \'"\'{src}\'"\' to \'"\'{dst}\'"\' because there are unsaved changes; exit 1;;
    esac
elif test -e {dst}; then
    ${{SHTOOL}} echo cannot copy \'"\'{src}\'"\' to \'"\'{dst}\'"\' because the target exists
    exit 1
fi
'''.format(lineno=0, filename='abc', sha1hashes=sha1hashes, src=src, dst=dst)
    return ret


def generate_link_check(relativeto, link):
    src, dst = safe_src_dst(link)
    sha1hashes = sha1_cases(relativeto, link.src)
    ret = '''# Generated from line number {lineno} in {filename}
if test -L {dst} && test `readlink -f {src}` != `readlink -f {dst}`; then
    ${{SHTOOL}} echo cannot link '"'{dst}'"' to '"'{src}'"' because the link points elsewhere
    exit 1
elif test -L {dst}; then
    true
elif test -f {dst}; then
    case `dshash {dst}` in
        {sha1hashes}*) ${{SHTOOL}} echo cannot link \'"\'{dst}\'"\' to \'"\'{src}\'"\' because there are unsaved changes; exit 1;;
    esac
elif test -e {dst}; then
    ${{SHTOOL}} echo cannot link '"'{dst}'"' to '"'{src}'"' because the destination exists
    exit 1
fi
'''.format(lineno=0, filename='abc', sha1hashes=sha1hashes, src=src, dst=dst)
    return ret


def generate_mkdir_check(relativeto, mkdir):
    dst = safe_dst(mkdir)
    ret  = '''# Generated from line number {lineno} in {filename}
if test -d {dst}; then
    true
elif test -e {dst}; then
    ${{SHTOOL}} echo cannot mkdir '"'{dst}'"' because something exists
    exit 1
fi
'''.format(lineno=0, filename='abc', dst=dst)
    return ret


def generate_copy_action(relativeto, copy):
    src, dst = safe_src_dst(copy)
    return '${{SHTOOL}} install -m - -C {src} {dst}'.format(src=src, dst=dst)


def generate_link_action(relativeto, link):
    src, dst = safe_src_dst(link)
    return '''if test '!' {src} -ef {dst}; then
    ${{SHTOOL}} mkln -s {src} {dst}
fi'''.format(src=src, dst=dst)


def generate_mkdir_action(relativeto, mkdir):
    dst = safe_dst(mkdir)
    return '${{SHTOOL}} mkdir -p {dst}'.format(dst=dst)


def shtoolize(outputfile):
    pipe = subprocess.Popen(['shtoolize', '-q', '-o', outputfile,
                             'echo', 'install', 'mkln', 'mkdir'])
    stdout, stderr = pipe.communicate()
    if pipe.returncode != 0:
        raise RuntimeError('error building shtool for distribution')



def shellscript(inputfile, actionlist):
    header = '''# Generated by deftsilo
RELATIVETO=`dirname $0`

if test -z "${RELATIVETO}"; then
    RELATIVETO=.
fi

SHTOOL=${RELATIVETO}/shtool

if test -z "${DESTDIR}"; then
    DESTDIR="${HOME}"
fi

dshash ()
{
    shasum $1 | awk '{print $1}'
}
'''
    relativeto = os.path.dirname(inputfile) or '.'
    checks = {Copy: generate_copy_check
             ,Link: generate_link_check
             ,Mkdir: generate_mkdir_check
             }
    checkscript = '\n'.join([checks[type(a)](relativeto, a) for a in actionlist])
    actions = {Copy: generate_copy_action
              ,Link: generate_link_action
              ,Mkdir: generate_mkdir_action
              }
    actionscript = '\n'.join([actions[type(a)](relativeto, a) for a in actionlist])
    script = header + '\n' + checkscript + '\n' +actionscript
    return script.strip() + '\n'


def deftsilo(inputfile):
    actions = parse(inputfile)
    for action in actions:
        if hasattr(action, 'src') and not os.path.exists(action.src):
            errstr = 'non-existent file "{0}" on line {1}'
            raise RuntimeError(errstr.format(action.src, action.lineno))
    shtool = os.path.join(os.path.dirname(inputfile), 'shtool')
    shtoolize(shtool)
    script = shellscript(inputfile, actions)
    output = os.path.join(os.path.dirname(inputfile), 'dotfiles.sh')
    with open(output, 'w') as fout:
        fout.write(script)
        fout.flush()
    tar = tarfile.open(os.path.join(os.path.dirname(inputfile), 'dotfiles.tar.gz'), 'w:gz')
    files = [a.src for a in actions if hasattr(a, 'src')]
    tar.add(inputfile, os.path.join('dotfiles', os.path.basename(inputfile)))
    tar.add(output, 'dotfiles/dotfiles.sh')
    tar.add(shtool, 'dotfiles/shtool')
    for filename in files:
        tar.add(os.path.join(os.path.dirname(inputfile), filename),
                os.path.join('dotfiles', filename))
    tar.close()


def main(args):
    parser = argparse.ArgumentParser(description='top-level descr')
    parser.add_argument('inputfile', type=str, help='input help')
    args = parser.parse_args(args)
    try:
        deftsilo(args.inputfile)
        return 0
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 1


if __name__ == '__main__':
    import sys
    try:
        sys.exit(main(sys.argv[1:]))
    except RuntimeError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
