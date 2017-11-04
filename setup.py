from setuptools import setup

setup(
    name = 'pytest-cassandra',
    py_modules = ['pytest_cassandra'],
    version = '0.1.0',
    description = (
        'Cassandra CCM Test Fixtures for pytest'
    ),
    author = 'Daniel Wozniak',
    author_email = 'dan@woz.io',
    url = 'https://github.com/dwoz/pytest-cassandra',
    download_url = 'https://github.com/dwoz/pytest-cassandra/archive/0.1.0.tar.gz',
    bugtrack_url = 'https://github.com/dwoz/pytest-cassandra/issues',
    keywords = [
        'testing', 'pytest', 'plugin', 'fixture', 'cassandra'
    ],
    entry_points = {
        'pytest11': [
            'cassandra = pytest_cassandra',
        ]
    },
    classifiers=[
        'Development Status :: 1 - Planning',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Topic :: Software Development :: Testing',
        'Topic :: Utilities',
        'Framework :: Pytest',
    ],
    install_requires=[
        'netifaces',
        'psutil',
        'cassandra-driver',
    ]
)
