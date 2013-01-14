#!/bin/bash
# IMPORTANT: Source RVM as a function into local environment.
#            Otherwise switching gemsets won't work.
[ -s "$HOME/.rvm/scripts/rvm" ] && . "$HOME/.rvm/scripts/rvm"
rvm use 1.8.7
cd ruby_dicom_cbmi
gem build dicom.gemspec
gem uninstall dicom --all
gem install dicom-0.8.6b.gem
cd ..
export RUBYOPT="rubygems"
ruby ruby_dicom_cbmi/scripts/anon_dicom.rb -m $5 -r "$1" -s -q $4 -v dicom_limited_vocab.json -d $2/ $3/
