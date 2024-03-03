deftsilo
========

deftsilo is a dotfiles manager that focuses on portability.  Deftsilo generates as an intermediary a shell script that
ensures portability and safety for updating dotfiles.  The resulting script will not overwrite dotfiles that have not
been checked into git.  For example, if `~/dotfiles` held dotfiles, we could do the following:

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

Documentation
-------------

The latest documentation is always available at [docs.rs](https://docs.rs/deftsilo/latest/deftsilo/).
