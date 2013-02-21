#!/bin/bash
# IMPORTANT: Source RVM as a function into local environment.
#            Otherwise switching gemsets won't work.
[ -s "$HOME/.rvm/scripts/rvm" ] && . "$HOME/.rvm/scripts/rvm"
rvm use 1.9.2
gem uninstall dicom --all
gem install dicom --no-ri --no-rdoc
export RUBYOPT="rubygems"
ruby dicom_tools/dicom_push.rb $1@$2:$3 $4
