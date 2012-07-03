from setuptools import setup

setup(name="sitedeploy",
      version="1.0",
      description="site deployment",
      long_description = open("README.rst").read(),
      keywords=("site, deploy, synchronize, ftp, ssh"),
      author="David Siroky",
      author_email="siroky@dasir.cz",
      url="http://www.smallbulb.net",
      license="MIT License",
      classifiers=[
          "Development Status :: 5 - Production/Stable",
          "Intended Audience :: Developers",
          "Intended Audience :: System Administrators",
          "License :: OSI Approved :: MIT License",
          "Topic :: System :: Networking",
          "Topic :: Internet :: WWW/HTTP :: Site Management",
          "Topic :: Software Development",
          "Topic :: Utilities"
        ],
      py_modules=["sitelib"],
      scripts=["sitedeploy.py", "sitecopy2sitedeploy.py"]
    )
