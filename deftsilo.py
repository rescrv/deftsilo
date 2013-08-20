#!/usr/bin/env python

# Copyright (c) 2012-2013, Robert Escriva
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
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import with_statement


import collections
import hashlib
import os
import os.path
import shlex
import subprocess
import sys
import tarfile
import tempfile

import argparse


__all__ = ['dotfile', 'link', 'main', 'mkdir', 'umask']


class ParseError(Exception): pass


Dotfile = collections.namedtuple('Dotfile', 'lineno src dst prefix action')
Mkdir = collections.namedtuple('Mkdir', 'lineno dst')


DESCRIPTION = '''deftsilo is a management tool for dotfiles.'''
HEADER = '''#!/bin/sh
# Generated by deftsilo
RELATIVETO=`dirname $0`

if test -z "${RELATIVETO}"; then
    RELATIVETO=.
fi

SHTOOL=${RELATIVETO}/shtool

if test -z "${DESTDIR}"; then
    DESTDIR="${HOME}"
fi

sha1hash ()
{
    shasum "$1" | awk '{print $1}'
}

'''

CHECKS = '#################################### CHECKS ####################################\n\n'
ACTIONS = '#################################### ACTIONS ###################################\n\n'


class NoExitParser(argparse.ArgumentParser):
    def error(self, message):
        raise ParseError(message)
    def exit(self, status=0, message=None):
        raise ParseError(message)


dotfile = NoExitParser()
dotfile.add_argument('--git', dest='action', action='store_const', const='git', default='git')
dotfile.add_argument('--copy', dest='action', action='store_const', const='copy')
dotfile.add_argument('--link', dest='action', action='store_const', const='link')
dotfile.add_argument('--prefix', '-p', dest='prefix', type=int, default=0)
dotfile.add_argument('src', type=str, default=None)
dotfile.add_argument('dst', nargs='?', type=str, default=None)


def add_dot_before_prefix(path, prefix):
    components = []
    for i in range(prefix):
        head, tail = os.path.split(path)
        components.append(tail)
        path = head
    out = '.' + os.path.basename(path)
    return os.path.join(out, *reversed(components))


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
        if sha1 == '0' * 40:
            continue
        shapipe = subprocess.Popen(["git", "cat-file", "blob", sha1],
                    shell=False, stdout=subprocess.PIPE)
        stdout, stderr = shapipe.communicate()
        ret.append(hashlib.sha1(stdout).hexdigest())
    return ret


def parse_dotfile(lineno, cmd):
    args = dotfile.parse_args(cmd)
    return Dotfile(lineno=lineno, src=args.src, dst=args.dst,
                   prefix=args.prefix, action=args.action)


def parse_mkdir(lineno, cmd):
    return Mkdir(lineno=lineno, dst=cmd)


def parse_line(lineno, args):
    assert len(args) > 0
    if args[0] == 'dotfile':
        return parse_dotfile(lineno, args[1:])
    elif args[0] == 'mkdir':
        return parse_mkdir(lineno, args[1:])
    else:
        errstr = 'unknown command "{0}" on line {1}'
        raise ParseError(errstr.format(args[0], lineno))


def parse(inputfile):
    source = open(inputfile).read()
    actions = []
    command = ''
    lineno = 1
    continuation = False
    for i, line in enumerate(source.split('\n')):
        if not continuation:
            lineno = i + 1
        if line.endswith('\\') and len(line) > 0:
            command += line[:-1] + ' '
            continuation = True
        else:
            command += line
            args = shlex.split(command, posix=True)
            newargs = []
            for arg in args:
                if arg.startswith('#'):
                    break
                newargs.append(arg)
            args = newargs
            command = ''
            continuation = False
            if args:
                try:
                    actions.append(parse_line(lineno, args))
                except ParseError as e:
                    e.lineno = lineno
                    raise e
    return actions


def validate(inputfile, gitaction, actions):
    for action in actions:
        if hasattr(action, 'src'):
            path = os.path.join(os.path.dirname(inputfile), action.src)
            if not os.path.exists(path):
                errstr = 'non-existent file "{0}" on line {1}'
                raise RuntimeError(errstr.format(action.src, action.lineno))
            if os.path.isdir(path) and gitaction != 'link':
                errstr = 'dotfile "{0}" is a directory on line {1}'
                raise RuntimeError(errstr.format(action.src, action.lineno))


def shell_escape(path):
    return path


def shell_src(path):
    return '"${RELATIVETO}"/' + shell_escape(path)


def shell_dst(path):
    return '"${DESTDIR}"/' + shell_escape(path)


def generate_mkdir_check(inputfile, gitaction, mkdir):
    ret = []
    for d in mkdir.dst:
        dst = shell_dst(d)
        templ = '''# generated from {filename}:{lineno}
if test -d {dst}; then
    true
elif test -e {dst}; then
    ${{SHTOOL}} echo cannot mkdir '"'{dst}'"' because something exists
    exit 1
fi\n'''
        ret.append(templ.format(lineno=mkdir.lineno, filename=inputfile, dst=dst))
    return '\n'.join(ret)


def generate_dotfile_check(inputfile, gitaction, dotfile):
    relativeto = os.path.dirname(inputfile) or '.'
    sha1hashes = get_sha1s_for(relativeto, dotfile.src)
    sha1cases = ''.join([s + ') ;;\n' + ' ' * 8 for s in sha1hashes])
    src = shell_src(dotfile.src)
    dst = shell_dst(dotfile.dst or
                    add_dot_before_prefix(dotfile.src, dotfile.prefix))
    templ = '''# generated from {filename}:{lineno}
if test -L {dst} && test `readlink -f {src}` != `readlink -f {dst}`; then
    ${{SHTOOL}} echo cannot install '"'{src}'"' because it would replace a link that points elsewhere.
    exit 1
elif test -L {dst}; then
    true
elif test -f {dst}; then
    case `sha1hash {dst}` in
        {sha1cases}*) ${{SHTOOL}} echo install \'"\'{src}\'"\' because there are unsaved changes; exit 1;;
    esac
elif test -e {dst}; then
    ${{SHTOOL}} echo install '"'{src}'"' because the destination exists
    exit 1
fi
'''
    return templ.format(filename=inputfile,
                        lineno=dotfile.lineno,
                        sha1cases=sha1cases,
                        src=src, dst=dst)


def generate_mkdir_action(inputfile, gitaction, mkdir):
    ret = ['# generated from {filename}:{lineno}'
           .format(lineno=mkdir.lineno, filename=inputfile)]
    for d in mkdir.dst:
        dst = shell_dst(d)
        templ = '${{SHTOOL}} mkdir -p {dst}'
        ret.append(templ.format(dst=dst))
    return '\n'.join(ret) + '\n'


def generate_dotfile_action(inputfile, gitaction, dotfile):
    action = dotfile.action
    if action == 'git':
        action = gitaction
    assert action in ('link', 'copy')
    src = shell_src(dotfile.src)
    dst = shell_dst(dotfile.dst or
                    add_dot_before_prefix(dotfile.src, dotfile.prefix))
    head = '# generated from {filename}:{lineno}\n' \
           .format(lineno=dotfile.lineno, filename=inputfile)
    if action == 'link':
        return head + '''if test '!' {src} -ef {dst}; then
    ${{SHTOOL}} mkln -f -s {src} {dst}
fi\n'''.format(src=src, dst=dst)
    if action == 'copy':
        return head + '${{SHTOOL}} install -m - -C {src} {dst}\n'.format(src=src, dst=dst)


def shellscript(inputfile, actionlist, gitaction):
    assert gitaction in ('link', 'copy')
    checks = {Mkdir: generate_mkdir_check,
              Dotfile: generate_dotfile_check}
    checkscript = '\n'.join([checks[type(a)](inputfile, gitaction, a)
                             for a in actionlist])
    actions = {Mkdir: generate_mkdir_action,
               Dotfile: generate_dotfile_action}
    actionscript = '\n'.join([actions[type(a)](inputfile, gitaction, a)
                              for a in actionlist])
    script = HEADER + '\n' + CHECKS + checkscript + '\n' + ACTIONS + actionscript
    return script.strip() + '\n'


def shtoolize(outputfile):
    if os.path.exists(outputfile):
        return
    pipe = subprocess.Popen(['shtoolize', '-q', '-o', outputfile,
                             'echo', 'install', 'mkln', 'mkdir'])
    stdout, stderr = pipe.communicate()
    if pipe.returncode != 0:
        raise RuntimeError('error building shtool for distribution')


def runfromgit(inputfile):
    actions = parse(inputfile)
    validate(inputfile, 'link', actions)
    script = shellscript(inputfile, actions, gitaction='link')
    pipe = subprocess.Popen(['sh'], cwd=os.path.dirname(inputfile) or '.',
                            shell=False, stdin=subprocess.PIPE)
    pipe.stdin.write(script)
    pipe.stdin.close()
    pipe.wait()
    return pipe.returncode


def printscript(inputfile):
    actions = parse(inputfile)
    validate(inputfile, 'link', actions)
    script = shellscript(inputfile, actions, gitaction='link')
    print(script.strip())
    return 0


def createtarfile(inputfile, shtool):
    actions = parse(inputfile)
    validate(inputfile, 'copy', actions)
    script = shellscript(inputfile, actions, gitaction='copy')
    fout = tempfile.TemporaryFile()
    fout.write(script)
    fout.flush()
    fout.seek(0)
    tar = tarfile.open(os.path.join(os.path.dirname(inputfile), 'dotfiles.tar.gz'), 'w:gz')
    files = [a.src for a in actions if hasattr(a, 'src')]
    tinfo = tar.gettarinfo(arcname='dotfiles/dotfiles.sh', fileobj=fout)
    tar.add(inputfile, os.path.join('dotfiles', os.path.basename(inputfile)))
    tar.addfile(tinfo, fout)
    tar.add(shtool, 'dotfiles/shtool')
    for filename in sorted(files, key=(lambda x: (x.src if hasattr(x, 'src') else ''))):
        tar.add(os.path.join(os.path.dirname(inputfile), filename),
                os.path.join('dotfiles', filename))
    tar.close()
    return 0


def main(args):
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument('action', type=str, choices=('run', 'show', 'tar'),
                        help='how to process the manifest')
    parser.add_argument('manifest', type=str,
                        help='the manifest to process')
    args = parser.parse_args(args)
    try:
        shtool = os.path.join(os.path.dirname(args.manifest), 'shtool')
        shtoolize(shtool)
        if args.action == 'run':
            return runfromgit(args.manifest)
        if args.action == 'show':
            return printscript(args.manifest)
        elif args.action == 'tar':
            return createtarfile(args.manifest, shtool)
        else:
            raise RuntimeError("Unknown action %r" % args.action)
    except ParseError as e:
        print('error on line {0}: {1}'.format(e.lineno, e), file=sys.stderr)
        return -1
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return -1


if __name__ == '__main__':
    import sys
    try:
        sys.exit(main(sys.argv[1:]))
    except RuntimeError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
