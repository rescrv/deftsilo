from distutils.core import setup


classifiers = [ 'Development Status :: 4 - Beta'
              , 'Intended Audience :: Developers'
              , 'License :: OSI Approved :: BSD License'
              , 'Operating System :: MacOS :: MacOS X'
              , 'Operating System :: POSIX :: Linux'
              , 'Operating System :: Unix'
              , 'Programming Language :: Python :: 2.6'
              , 'Programming Language :: Python :: 2.7'
              ]

setup(name='Deftsilo',
      version='0.1',
      author='Robert Escriva (rescrv)',
      author_email='deftsilo@mail.robescriva.com',
      py_modules=['deftsilo'],
      scripts=['bin/deftsilo'],
      license='3-clause BSD',
      url='http://robescriva.com/',
      description='Easy, portable dotfiles management.',
      classifiers=classifiers,
      )
