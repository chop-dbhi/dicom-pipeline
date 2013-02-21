#!/bin/bash
# IMPORTANT: Source RVM as a function into local environment.
#            Otherwise switching gemsets won't work.
[ -s "$HOME/.rvm/scripts/rvm" ] && . "$HOME/.rvm/scripts/rvm"
rvm use 1.9.2
cd ruby_dicom
gem build dicom.gemspec
gem uninstall dicom --all
gem install dicom-0.9.3.gem --no-ri --no-rdoc
cd ..
export RUBYOPT="rubygems"
ruby dicom_tools/dicom_push.rb $1@$2:$3 $4
