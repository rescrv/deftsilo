deftsilo
========

deftsilo is a powerful and minimalistic dotfiles management tool written in Rust.  It enables power users to easily
synchronize their home directory dotfiles (deftsilo is an anagram for dotfiles), ensuring consistency across systems.
The chief problem it solves is the bootstrap problem:  While the build-time dependencies include Rust and git, the
output is a POSIX-compatible shell script that will install the files by copying them or by creating a symlink farm.
Consequently one can export dotfiles to systems without Rust or git.  That last bit's become less important with the
advent of container-based computing, but it's still handy to bootstrap a new machine every few years without having to
do anything special.

Key Features
------------

- **Platform-agnostic synchronization:** Generates POSIX-compatible shell scripts for applying and managing dotfiles on
  popular UNIX-based systems like Linux, macOS, BSD, and others that support a POSIX-compatible shell.
- **Git integration:** Leverages Git to track changes and ensures that only files checked into the repository are
  overwritten or over-linked during synchronization.  This prevents accidental loss of data and enables easy recovery
  using Git's version control capabilities.
- **Build-time dependency on Rust and Git:** At runtime, deftsilo relies solely on a UNIX shell environment.  It has a
  build-time dependencies on stable Rust and the Git command-line client.
- **Zero-configuration synchronization (almost):** Once set up with a Git repository containing desired dotfiles,
  running `deftsilo` from the root of the repository generates an install script that can be used to synchronize files.

Target audience
---------------

Experienced UNIX users and power users who want an almost-zero-configuration way to manage their dotfiles and ensure
consistency across multiple machines. This tool is particularly suitable for developers who wish to maintain a single
source of truth for their home directory.

Usage
-----

For example, if `~/dotfiles` held dotfiles, we could do the following:

```console
cargo run -- --path ~/dotfiles
```

which would generate, in part, this script:

```console
deftsilo_mkdir ".ssh" 775
deftsilo_mkdir ".vim" 775
deftsilo_mkdir ".vim/colors" 775
deftsilo_mkdir ".vim/spell" 775
deftsilo_mkdir ".vim/syntax" 775
deftsilo_mkdir ".zkbd" 775
deftsilo_mkdir "bin" 775
deftsilo_mkdir "mail" 775
deftsilo_install ".gitconfig" 664 089886a87f7c859b19764957a029c69bcbe120fa0d0388c256205b5fdaf4529a 089886a87f7c859b19764957a029c69bcbe120fa0d0388c256205b5fdaf4529a 1b4afc46b49c07cab0339a83cd8c3105d39f43d7aa25f0df6674c40737b15f7c 1b4afc46b49c07cab0339a83cd8c3105d39f43d7aa25f0df6674c40737b15f7c 83d75106ccfd35c9c50b926cdc13e54cad4027837f27b990c5ec2d2c07d7ab33 bd3d940866bb88a53d13292a58d233951ad5ec2e544724a96abcec75791777de fab34430cb6000a8bf387490976088a83cf18d44b1597e6f8c8574bbfbfff2eb bc5f7f1873058329c496269c1c286d134bbd8e0c8cc692e3fc95cd29fceb9059
```

Omitted from this output is the preamble that defines the `deftsilo_mkdir` and `deftsilo_install` commands.  We can see
that the install of `.gitconfig` lists several sha256sum hashes.  Deftsilo will only overwrite `.gitconfig` if it
matches one of these hashes.  In this way, you can manage dotfiles on multiple machines and be warned if a change would
overwrite a file that's never been checked into version control.  The `-l` flag can be provided to link files instead of
copy.

You can run the unit tests of the deftsilo script to test portability to your platform with:

```console
cargo run -- --test >! test.sh && /bin/sh test.sh testing-dir
```

Status
------

Active development and testing.

Scope
-----

This crate provides the deftsilo tool for generating portable dotfiles-installing shell scripts.

Q & A
-----

1. **What is the license for `deftsilo`?**  deftsilo is licensed under the BSD license.

2. **What platforms are supported by `deftsilo`?**  deftsilo is written in Rust and should be portable to any platform
   that supports Rust.  The output is portable POSIX-compliant shell script.

3. **How does `deftsilo` handle permissions and ownership for created directories and installed files?**  deftsilo uses
   the `copy` or `ln -s` commands to install files and inherits behavior accordingly.

4. **What happens when the hashes don't match?**  If the current file does not match any of the provided hashes,
   deftsilo will loudly fail immediately and short-circuit the rest of the script.

5. **Are there any known limitations or edge cases to be aware of?**  deftsilo does not know about case-insensitive
   filesystems.  It will not warn you if you are about to overwrite a file that differs only in case.

6. **How is the generated shell script validated?**  `deftsilo --test` will generate as output the unit tests for the
   generated script.  Invoke it with `deftsilo --test > unittest.sh && /bin/my-shell unittest.sh`.

7. **Are there any plans or ideas for future developments?**  I'm soliciting feedback here.  I rarely change my
   dotfiles, so there's little need to interact with this when it works.

8. **How can users provide feedback or report issues?**  Clone the github repo and email me at the address in the
   changelog.

Documentation
-------------

The latest documentation is always available at [docs.rs](https://docs.rs/deftsilo/latest/deftsilo/).
